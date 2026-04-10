import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_websocket_permissions
from cat.log import log
from cat.looking_glass import StrayCat
from cat.services.memory.messages import UserMessage

router = APIRouter(tags=["Websocket"])


async def _safe_send_error(websocket: WebSocket, stray_cat: StrayCat, error: str) -> bool:
    if websocket.client_state == WebSocketState.DISCONNECTED:
        return False
    try:
        await stray_cat.notifier.send_error(error)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


@router.websocket("/ws")
@router.websocket("/ws/{agent_id}")
@router.websocket("/ws/{agent_id}/{chat_id}")
async def websocket_chat(
    websocket: WebSocket,
    info: AuthorizedInfo = check_websocket_permissions(AuthResource.CHAT, AuthPermission.WRITE),
):
    """
    Endpoint to handle incoming WebSocket connections, process messages, and stream responses.

    Keepalives: clients may send either plain text ``ping`` or the JSON string
    ``"ping"`` (with quotes).  Either form is accepted and answered with a
    plain-text ``pong``.  Any other message must be a JSON object matching
    :class:`~src.models.AskPayload`.

    LLM tokens are streamed to the client as ``{"token": "…"}`` frames while
    the final, complete answer is delivered as ``{"response": "…"}``.
    """
    stray_cat = info.stray_cat or await StrayCat.from_cat(user_data=info.user, cat=info.cheshire_cat)

    # Establish connection
    await websocket.accept()

    # Add the new WebSocket connection to the manager.
    websocket_manager = info.lizard.websocket_manager
    websocket_manager.add_connection(stray_cat.id, websocket)
    try:
        # Process messages
        while True:
            # receive_text() is used deliberately so that plain-text keepalives
            # (e.g. ws.send("ping")) reach the ping/pong guard below without
            # triggering a JSON decode error first.
            raw = await websocket.receive_text()

            # --- keepalive handling (accepts both plain text and JSON string) ---
            stripped = raw.strip()
            if stripped in ("ping", '"ping"'):
                await websocket.send_text("pong")
                continue
            if stripped in ("pong", '"pong"'):
                continue

            # --- parse JSON and validate payload ---
            try:
                payload = json.loads(raw)
                user_message = UserMessage(**payload)
            except json.JSONDecodeError as exc:
                log.error(f"Invalid JSON received over WebSocket: {exc}")
                if not await _safe_send_error(websocket, stray_cat, f"Invalid JSON: {exc}"):
                    break
                continue
            except Exception as exc:
                log.error(f"Invalid payload received over WebSocket: {exc}")
                if not await _safe_send_error(websocket, stray_cat, f"Invalid payload: {exc}"):
                    break
                continue

            # asyncio.shield keeps the LLM call alive even if the outer task is cancelled
            # (e.g. on server shutdown or mid-stream client disconnect), so the response is
            # still fully processed and persisted to memory.
            await asyncio.shield(stray_cat.run_websocket(user_message))
    except WebSocketDisconnect:
        log.info(f"WebSocket connection closed for conversation {stray_cat.id}")
    except asyncio.CancelledError:
        log.info(f"WebSocket handler cancelled for conversation {stray_cat.id}; ongoing LLM call will complete")
        raise  # propagate so the server can finish its shutdown sequence
    finally:
        # Remove connection on disconnect
        if websocket.client_state != WebSocketState.DISCONNECTED:
            websocket_manager.close_connection(stray_cat.id)
        else:
            websocket_manager.remove_connection(stray_cat.id)
