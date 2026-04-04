# Performance Optimization Report — `cat/`

> Revision: April 2, 2026  
> Already implemented: WebSocket Redis Pub/Sub cross-replica delivery

---

## Summary table

| #  | Area                                                             | File(s)                                       | Impact      | Effort  |
|----|------------------------------------------------------------------|-----------------------------------------------|-------------|---------|
| 1  | Parallelize DECLARATIVE + EPISODIC recalls                       | `stray_cat.py`                                | 🔴 Critical | Low     |
| 2  | Parallelize recall + procedures fetch                            | `stray_cat.py`                                | 🔴 Critical | Low     |
| 3  | Make `execute_hook` async-native                                 | `utils.py`, `mad_hatter.py`                   | 🟠 High     | Medium  |
| 4  | Migrate Redis client to `redis.asyncio` ⚠️ prerequisite for #9   | `database.py` + all cruds                     | 🟠 High     | High    |
| 5  | Batch `embed_documents` for procedures                           | `cheshire_cat.py`                             | 🟡 Medium   | Low     |
| 6  | Pipeline Redis reads in listing endpoints                        | `cruds/settings.py`, `cruds/conversations.py` | 🟡 Medium   | Low     |
| 7  | `embedder.size` — lazy initialisation with `@cached_property`    | `services/factory/embedder.py`                | 🟡 Medium   | Trivial |
| 8  | Remove `asyncio.sleep(0.1)` in Qdrant pagination                 | `factory/vector_db.py`                        | 🟢 Low      | Trivial |
| 9  | LangChain `InMemoryCache` → `RedisSemanticCache` *(requires #4)* | `routes/routes_utils.py`                      | 🟢 Low      | Low     |
| 10 | `asyncio.shield` LLM calls in WebSocket                          | `routes/websocket.py`                         | 🟢 Low      | Trivial |

---

## 1 🔴 Parallelize DECLARATIVE + EPISODIC recalls

**File:** `cat/looking_glass/stray_cat.py` — `recall_context_to_working_memory()`

Two independent Qdrant queries are awaited sequentially. They hit different collections and share no state.

```python
# BEFORE — sequential (100–300 ms wasted per turn)
agent_memories = await self._agentic_workflow.context_retrieval(
    collection=VectorMemoryType.DECLARATIVE, params=config,
)
chat_memories = await self._agentic_workflow.context_retrieval(
    collection=VectorMemoryType.EPISODIC,
    params=config.model_copy(deep=True, update={"metadata": {"chat_id": self.id}}),
)
```

```python
# AFTER — parallel
agent_memories, chat_memories = await asyncio.gather(
    self._agentic_workflow.context_retrieval(
        collection=VectorMemoryType.DECLARATIVE, params=config,
    ),
    self._agentic_workflow.context_retrieval(
        collection=VectorMemoryType.EPISODIC,
        params=config.model_copy(deep=True, update={"metadata": {"chat_id": self.id}}),
    ),
)
```

**Saving:** ~100–300 ms per conversation turn (one full vector-search RTT).

---

## 2 🔴 Parallelize recall + procedures fetch

**File:** `cat/looking_glass/stray_cat.py` — `__call__()`

`recall_context_to_working_memory` (DECLARATIVE + EPISODIC) and `get_procedures` (PROCEDURAL) query completely independent Qdrant collections yet run back-to-back. The `after_cat_recalls_memories` hook only needs the recall result, so it still runs in the correct order.

```python
# AFTER — PROCEDURAL fetch starts immediately, overlapping with DECL+EPIS
procedures_task = asyncio.ensure_future(self.get_procedures(config))

await self.recall_context_to_working_memory(config)   # waits only for DECL+EPIS

self.plugin_manager.execute_hook("after_cat_recalls_memories", config, caller=self)

agent_output = plugin_manager.execute_hook("agent_fast_reply", caller=self)
if agent_output:
    procedures_task.cancel()
    return CatMessage(text=agent_output.output)

tools = await procedures_task   # very likely already done by now
```

**Saving:** another ~100–150 ms per turn (PROCEDURAL query overlaps with recalls + hooks).

---

## 3 🟠 Make `execute_hook` async-native

**Files:** `cat/utils.py`, `cat/looking_glass/mad_hatter/mad_hatter.py`

When a plugin hook is `async` and called from inside a running event loop, `run_sync_or_async` currently:
1. Detects the running loop.
2. Spawns a **brand-new OS thread**.
3. Creates a **brand-new `asyncio` event loop** inside that thread.
4. Blocks the caller via `thread.join()`.

This serialises async hooks and adds thread-creation overhead on every hook call.

**Fix — add `execute_hook_async` to `MadHatter`:**

```python
async def execute_hook_async(self, hook_name: str, *args, caller: "ContextMixin") -> Any:
    if hook_name not in self.hooks:
        raise Exception(f"Hook {hook_name} not present in any plugin")

    tea_cup = utils.safe_deepcopy(args[0]) if args else None

    for hook in self.hooks[hook_name]:
        try:
            kwargs = {self.context_execute_hook: caller}
            hook_args = (utils.safe_deepcopy(tea_cup), *utils.safe_deepcopy(args[1:])) if args else ()

            if asyncio.iscoroutinefunction(hook.function):
                tea_spoon = await hook.function(*hook_args, **kwargs)        # direct await
            else:
                tea_spoon = await asyncio.to_thread(                         # offload sync hook
                    functools.partial(hook.function, *hook_args, **kwargs)
                )

            if tea_spoon is not None:
                tea_cup = tea_spoon
        except Exception as e:
            log.error(f"Error in plugin {hook.plugin_id}::{hook.name}: {e}")
            log.warning(self.plugins[hook.plugin_id].plugin_specific_error_message())

    return tea_cup
```

Then replace `execute_hook(...)` with `await execute_hook_async(...)` in all `async` call sites (`stray_cat.py`, `cheshire_cat.py`). The existing synchronous `execute_hook` stays for sync call sites in `BillTheLizard.__init__`.

**Saving:** removes 1–2 OS thread creations + event-loop instantiations per async hook.

---

## 4 🟠 Migrate Redis client to `redis.asyncio` ⚠️ prerequisite for #9

**Files:** `cat/db/database.py`, `cat/db/crud.py`, all `cat/db/cruds/*.py`

`Database` wraps a **synchronous `redis.Redis`** client. Every CRUD call blocks the FastAPI event loop thread while waiting for a network round-trip (~0.5–5 ms each). With 30+ call sites across every request this prevents the event loop from handling other connections during those waits.

`redis.asyncio.Redis` is already bundled in `redis-py ≥ 4.2` — **no new dependency**.

```python
# db/database.py
import redis.asyncio as aioredis

@singleton
class Database:
    def __init__(self):
        self.db = self._build_client()

    def _build_client(self) -> aioredis.Redis:
        host = get_env("CAT_REDIS_HOST")
        password = get_env("CAT_REDIS_PASSWORD")
        tls = get_env_bool("CAT_REDIS_TLS")
        kwargs = dict(
            host=host, port=get_env_int("CAT_REDIS_PORT"),
            db=get_env_int("CAT_REDIS_DB"),
            decode_responses=True, ssl=tls,
        )
        if password:
            kwargs["password"] = password
        return aioredis.Redis(**kwargs)
```

All CRUD functions become `async def` and `await` every Redis call.  
`startup.py` must change `get_db().close()` → `await get_db().aclose()`.

> ⚠️ Highest-effort item — touches ~30 files — but changes are purely mechanical (`async`/`await`). Recommended as a dedicated commit with full test run.

**Saving:** fully unblocks the event loop for all Redis I/O.

---

## 5 🟡 Batch `embed_documents` for procedures

**File:** `cat/looking_glass/cheshire_cat.py` — `embed_procedures()`

The current list comprehension calls `embedder.embed_query(text)` once per procedure trigger — N serial embedding RTTs.

```python
# AFTER — single batched call
triggers = [
    (t, p)
    for p in self.plugin_manager.procedures
    for t in p.to_document_recall()
    if pt is None or p.type == pt
]
if not triggers:
    return

texts   = [t.document.page_content for t, _ in triggers]
vectors = await asyncio.to_thread(self.lizard.embedder.embed_documents, texts)

points = [
    PointStruct(
        id=uuid.uuid4().hex,
        payload=t.document.model_dump(),
        vector=vector,
    )
    for (t, _), vector in zip(triggers, vectors)
]
```

**Saving:** reduces N embedding RTTs to 1 during plugin activation and agent bootstrap.

---

## 6 🟡 Pipeline Redis reads in listing endpoints

**Files:** `cat/db/cruds/settings.py` (`get_agents()`), `cat/db/cruds/conversations.py` (`get_conversations_attributes()`)

Both functions do `scan_iter` then individual `get()` per key — **N+1 round-trips**.

```python
# AFTER — single pipeline round-trip
async def get_agents(db) -> list[dict]:
    keys = [k async for k in db.scan_iter(f"{AGENT_PREFIX}:*")]
    if not keys:
        return []
    results = await db.json().mget(keys, "$")
    return [r[0] for r in results if r]
```

**Saving:** N Redis RTTs → 1 per listing call.

---

## 7 🟡 `embedder.size` — lazy initialisation with `@cached_property`

**File:** `cat/services/factory/embedder.py`

`size` calls `self.embed_query("hello world")` — a full model forward pass — on **every access**. Multiple accesses within the same embedder instance's lifetime (e.g. inside `embed_all_in_cheshire_cats` and `check_embedding_size`) each re-run the inference.

`@cached_property` is purely **instance-level lazy initialisation**: the result is computed once when first accessed and stored on that instance. It is never shared across instances, across requests, or across nodes — no synchronisation needed.

```python
from functools import cached_property

# BEFORE
@property
def size(self) -> int:
    return len(self.embed_query("hello world"))

# AFTER
@cached_property
def size(self) -> int:
    return len(self.embed_query("hello world"))
```

**Saving:** eliminates redundant embedding calls within the same instance's scope.

---

## 8 🟢 Remove `asyncio.sleep(0.1)` from Qdrant pagination

**File:** `cat/services/factory/vector_db.py` — `_get_all_points()`

100 ms of pure idle time is injected between every pagination batch. Qdrant's async client applies natural backpressure through TCP flow control.

```python
# Remove this line entirely:
await asyncio.sleep(0.1)
```

**Saving:** 100 ms × (pages − 1) per full-collection scan.

---

## 9 🟢 LangChain `InMemoryCache` → `RedisSemanticCache` *(requires #4)*

**File:** `cat/routes/routes_utils.py` — `startup_app()`

`InMemoryCache` is per-process: identical LLM prompts answered on different Swarm replicas get no cache hit. `RedisSemanticCache` is shared across all replicas and expires automatically.

Requires item #4 (async Redis client) since LangChain's Redis cache integrations use async Redis internally.

```python
from langchain_community.cache import RedisSemanticCache
from cat.db.database import get_db_connection_string

# AFTER
set_llm_cache(
    RedisSemanticCache(
        redis_url=get_db_connection_string(),
        embedding=BillTheLizard().embedder,
        score_threshold=0.95,
    )
)
```

**Saving:** cross-replica LLM response reuse for identical/near-identical prompts.

---

## 10 🟢 Shield LLM calls from WebSocket disconnects

**File:** `cat/routes/websocket.py`

A client disconnect cancels the WebSocket handler coroutine, propagating `CancelledError` into the in-flight LLM call. The model call is aborted mid-stream and `after_cat_sends_message` hooks never run.

```python
try:
    await asyncio.shield(stray_cat.run_websocket(user_message))
except asyncio.CancelledError:
    pass  # client left; shielded task completes cleanly in the background
```

**Saving:** correct hook lifecycle and clean LLM call completion even on abrupt disconnects.

---

## Priority checklist

| Priority  | Action                                  | Expected gain                               |
|-----------|-----------------------------------------|---------------------------------------------|
| ✅ Done    | WebSocket Redis Pub/Sub                 | Cross-replica delivery                      |
| 🔴 P0     | #1 — Parallelize DECLARATIVE + EPISODIC | −100–300 ms/turn                            |
| 🔴 P0     | #2 — Parallelize recall + procedures    | −100–150 ms/turn                            |
| 🟠 P1     | #3 — `execute_hook_async`               | Remove OS thread per async hook             |
| 🟠 P1     | #4 — Migrate to `redis.asyncio`         | Unblock event loop entirely                 |
| 🟡 P2     | #5 — Batch `embed_documents`            | −(N−1) embed calls at startup/plugin change |
| 🟡 P2     | #6 — Pipeline Redis listing reads       | −(N−1) RTTs per list call                   |
| 🟡 P2     | #7 — `embedder.size` `@cached_property` | Eliminate redundant in-instance inference   |
| 🟢 P3     | #8 — Remove pagination sleep            | −100 ms/page on large collections           |
| 🟢 P3     | #9 — `RedisSemanticCache` *(after #4)*  | Cross-replica LLM response reuse            |
| 🟢 P3     | #10 — `asyncio.shield` in WebSocket     | Correct hook lifecycle on disconnect        |
