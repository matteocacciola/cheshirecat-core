# Cheshire Cat: AI agent as a microservice

![GitHub Repo stars](https://img.shields.io/github/stars/matteocacciola/cheshirecat-core?style=social)
![GitHub Release](https://img.shields.io/github/v/release/matteocacciola/cheshirecat-core)
![GitHub commits since latest release](https://img.shields.io/github/commits-since/matteocacciola/cheshirecat-core/latest)
![GitHub issues](https://img.shields.io/github/issues/matteocacciola/cheshirecat-core)
![GitHub Release Date](https://img.shields.io/github/release-date/matteocacciola/cheshirecat-core.svg)
![GitHub tag (with filter)](https://img.shields.io/github/v/tag/matteocacciola/cheshirecat-core)
![GitHub top language](https://img.shields.io/github/languages/top/matteocacciola/cheshirecat-core)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/matteocacciola/cheshirecat-core)

# Why use the Cheshire Cat?
The Cheshire Cat is a framework to build custom AI agents:

- ⚡️ API first, to easily add a conversational layer to your app
- 💬 Chat via WebSocket and manage your agent with an customizable REST API
- 🐘 Built-in RAG with **customizable vector database**, so you can use your own technology (e.g., Qdrant, Pinecone, Weaviate, etc.)
- 🐘 Customizable resources for your documents, so that you can use your own storage (e.g., S3, MinIO, etc.)
- 🌐 Customizable integration of **MCP clients**, such as LangSmith or LlamaIndex 
- 🕐 History of conversations and documents, to make your agent smarter
- 🧩 Plugin system to easily extend the core functionality
- 🧩 Built-in plugins
  - 🪛 Extend core components (file managers, LLMs, vector databases)
  - ✂️ Customizable chunking and embedding
  - 🛠 Custom tools, forms, endpoints, MCP clients
  - 🪛 LLM callbacks
- 🏛 Easy to use Admin Panel (available with the repository [matteocacciola/cheshirecat-admin](https://www.github.com/matteocacciola/cheshirecat-admin))
- 🌍 Supports any language model via langchain
- 👥 Multiuser with granular permissions, compatible with any identity provider
- 💬 Multi-chatbots, with configurable (even different) LLM, chunking strategy and other features per chatbot, plus specific knowledge per chatbot
- 💬 Remembers conversations and documents and uses them in conversation
- ☁️ Cloud Ready, working even with horizontal autoscaling
- 🐋 100% dockerized
- 🦄 Easy to understand [docs](https://deepwiki.com/matteocacciola/cheshirecat-core)

We are committed to openness, privacy and creativity, we want to bring AI to the long tail. If you want to know more
about our vision and values, read the [Code of Ethics](CODE-OF-ETHICS.md).

# Quickstart
To make Cheshire Cat run on your machine, you just need [`docker`](https://docs.docker.com/get-docker/) installed:

```bash
docker run --rm -it -p 1865:80 ghcr.io/matteocacciola/cheshirecat-core:latest
```
- Chat with the Cheshire Cat by downloading the [Admin Panel](https://www.github.com/matteocacciola/cheshirecat-admin) or by using the
  [widget](https://www.github.com/matteocacciola/cheshirecat-widget-vue).
- Try out the REST API on [localhost:1865/docs](http://localhost:1865/docs).

Since this version is intended as a microservice, the `admin` panel is no longer automatically installed with the package.

As a first thing, set the **Embedder** for the Cheshire Cat. A favourite **LLM** must be set for each chatbot; each chatbot can have
its own language model, with custom settings.
Everything can be done via the [Admin Panel](https://www.github.com/matteocacciola/cheshirecat-admin) or via the REST API endpoints.

Enjoy the Cheshire Cat!  
Follow instructions on how to run it with [docker compose and volumes](https://cheshire-cat-ai.github.io/docs/quickstart/installation-configuration/).

# Admin panel and UI widget
You can install an admin panel by using the [`cheshirecat-admin`](https://www.github.com/matteocacciola/cheshirecat-admin) repository.
The admin panel is a separate project that allows you to manage the Cheshire Cat and its settings, plugins, and chatbots.
It is built with Streamlit and is designed to be easy to use and customizable.

Moreover, a suitable widget for the current fork is available in [my Github account](https://github.com/matteocacciola/cheshirecat-widget-vue)
to chat the Cheshire Cat.

# API Usage

## For Streaming Responses (Real-time chat)
- **Use WebSocket connection** at `/ws`, `/ws/{agent_id}` or `/ws/{agent_id}/{chat_id}`; add the token or the API key as
a querystring parameter with the syntax `?token=...`
- Receive tokens in real-time as they're generated: message type `chat_token` for individual tokens; message type `chat`
for complete responses

## For Non-Streaming Responses (Simple API calls)
- **Use HTTP POST** to `/message`
- Receive complete response in single API call
- Better for integrations, batch processing, or simple request/response patterns

# Key differences of this version
The current version is a multi-tenant fork of the original [Cheshire Cat](https://www.github.com/cheshire-cat-ai/core). Here are the main differences:

## Multitenancy
The original version was designed to be a single-tenant application, meaning that it could only manage one chatbot at a time.
This version is designed to be multi-tenant, meaning that it can manage multiple chatbots at the same time, each with its own settings, plugins, LLMs, etc.
**The way of "injecting" the identification of the Chatbot (RAG) is simple**:
  - **in case of the HTTP API endpoints, use the `agent_id` key into the request headers or as a querystring parameter;**
  - **in case of the WebSocket API, use the `agent_id` into the URL, e.g., `/ws/{agent_id}`.**

## Cloud ready
This version can be deployed in a cluster environment. Whilst the original version stored the settings into
JSON files, **this version requires a Redis database** to store the settings, the conversation histories, the plugins and so
forth.

You can **configure the Redis database by environment variables**. The [`compose.yml`](./compose.yml) file is provided as an example. 
Hence, the current version is multi-tenant, meaning that you can manage multiple RAGs and other language models at the same time.

The Cheshire Cat is still stateless, so it can be easily scaled.  In case of a cluster environment, we suggest to use a shared storage,
mounted in the `cat/plugins` folder, to share the plugins.

A **RabbitMQ message broker** is recommended in a cluster environment, so that the installation
of plugins can be synchronized along all the PODs and the management of the Cheshire Cat can be done in a distributed way. Its
configuration is done via environment variables, too. The [`compose.yml`](./compose.yml) file is provided as an example.

## RAG Customization:
The original version used a fixed RAG implementation, meaning that it could only use a specific vector database and chunking strategy.
This version allows you to configure the RAG per chatbot, meaning that you can use your own vector database and chunking strategy.
- **The current version supports multiple vector databases**, such as Qdrant, Pinecone, Weaviate, etc.
- **The current version supports multiple chunking strategies**, such as text splitting or Semantic chunking.

## MCP clients
In this version, the Cheshire Cat can integrate several MCP clients, such as
[LangSmith](https://www.langchain.com/langsmith) or [LlamaIndex](https://www.llamaindex.ai/).
The original version did not support any MCP client.
MCP clients can be added via plugins, by using the `@mcp_client` decorator, similarly to the `@form` decorator.

```python
from typing import List, Any

from cat.mad_hatter.decorators import CatMcpClient, mcp_client


@mcp_client
class MyMcpClient(CatMcpClient):
    name = "your_mcp_client"
    description = "Description of your MCP Client"

    @property
    def init_args(self) -> List | Dict[str, Any]:
        """
        Define the input arguments to be passed to the constructor of the MCP client

        Returns:
            List of arguments, or a dictionary identifying each name of the arguments with the corresponding value
        """
        pass
```

## Security
The original project is developed as a framework that could be used for a personal use as well as for single-tenant production.
In the latter case, the original [documentation](https://cheshire-cat-ai.github.io/docs/) clearly states to set up a secure environment
by using an API Key. **If not configured properly (e.g. by setting up an API Key), the current version will not work, indeed**.
In this way, I tried to make the Cheshire Cat more secure and production-ready.

## Customizable LLM
The original version used a fixed LLM implementation, meaning that it could only use a specific language model.
This version allows you to configure the LLM per chatbot, meaning that you can use your own language model.
- **The current version supports multiple language models**, such as OpenAI, Ollama, Google, HuggingFace, etc.
- **The current version supports multiple LLMs**, meaning that you can use different language models for different chatbots.

## Customizable Storage
The original did not use any storage solution for the documents composing your RAG, meaning that you were able to store the documents into the knowledge base of each RAG, but not into a remote storage.
This version allows you to configure the storage per chatbot, meaning that you can use your own storage solution.
- **The current version supports multiple storage solutions**, such as S3, MinIO, etc.
- **The current version supports multiple file managers**, meaning that you can use different file managers for different chatbots.

## Customizable Chunking strategy
The original version used a fixed chunking strategy, meaning that it could only use a specific chunking strategy.
This version allows you to configure the chunking strategy per chatbot, meaning that you can use your own chunking strategy.
- **The current version supports multiple chunking strategies**, such as text splitting or Semantic chunking.
- **The current version supports multiple chunkers**, meaning that you can use different chunkers for different chatbots.
- **The current version supports the extension of the list of allowed chunkers**, so you can use your own chunking strategy.

## Customizable Vector Database
The original version used a fixed vector database, meaning that it could only use a specific vector database.
This version allows you to configure the vector database per chatbot, meaning that you can use your own vector database.
- **The current version supports multiple vector databases**, such as Qdrant, Pinecone, Weaviate, etc.
- **The current version supports multiple vector databases**, meaning that you can use different vector databases for different chatbots.
- **The current version supports the extension of the list of allowed vector databases**, so you can use your own vector database.

## Multiple chat histories
The original version did not store the chat histories, meaning that the chat history was lost when the chatbot was restarted.
This version stores the chat histories into the Redis database, meaning that the chat history is preserved even when the chatbot is restarted.

A consequence of this is that **the current version supports multiple chat histories**, meaning that you can have different chat histories for different chatbots.

## New features
Here, I have introduced some new features and improvements, such as:
- The `Embedder` is centralized and can be used by multiple RAGs and other language models.
- New API admin endpoints allowing to configure the `Embedder`.
- New API endpoints allowing to configure the `File Manager`, per chatbot.
- New API endpoints allowing to configure the chunking strategy, per chatbot.
- New API endpoints allowing to configure the vector database, per chatbot.
- A new event system that allows you to get fine-grained control over the AI.
- **The ability to manage multiple RAGs and other language models at the same time**.
- **The current version is agnostic to the vector database and chunking strategy**, meaning that you can use your own
  vector database and chunking strategy.
- The current version provides **histories of conversations and documents**.

## Compatibility with plugins
This new version is no more completely compatible with the original version, since the architecture has been deeply changed.
However, **most of the plugins developed for the original version should work with this version**.
Some plugins may require some changes to work with this version, since the architecture has been deeply changed.
In this case, please feel free to contact me for support.

## List of available hooks
The Cheshire Cat provides a set of hooks that can be used to customize the behavior of the AI agent. Hooks are events that can be
triggered at specific points in the conversation, allowing you to modify the behavior of the AI agent or to add custom functionality.
The list of available hooks is available in the [documentation](https://cheshire-cat-ai.github.io/docs/plugins/plugins/).
The current version introduces also the following additional hooks:

### Factories:
- `factory_allowed_file_managers`: to extend the list of allowed file managers
- `factory_allowed_chunkers`: to extend the list of allowed chunkers
- `factory_allowed_vector_databases`: to extend the list of allowed vector databases (so allowing to use your own vector database)

### Callbacks:
- `llm_callbacks`: add custom callbacks to the LangChain LLM/ChatModel

# Best practices

## Custom endpoints and permissions

When implementing custom endpoints, you can use the `@endpoint` decorator to create a new endpoint. Please, refer to the
[documentation](https://cheshire-cat-ai.github.io/docs/plugins/endpoints/) for more information.

> [!IMPORTANT]
> **Each endpoint implemented for chatbots must use the `check_permissions` method to authenticate**. See this
[`example`](https://github.com/matteocacciola/cheshirecat-core/blob/main/core/tests/mocks/mock_plugin/mock_endpoint.py#L30).
> 
> **Each endpoint implemented at a system level must use the `check_admin_permissions` method to authenticate**. See this
[`example`](https://github.com/matteocacciola/cheshirecat-core/blob/main/core/tests/mocks/mock_plugin/mock_endpoint.py#L35).

## Minimal plugin example

<details>
    <summary>
        Hooks (events)
    </summary>

```python
from cat.mad_hatter.decorators import hook


# hooks are an event system to get fine-grained control over your assistant
@hook
def agent_prompt_prefix(prefix, cat):
    prefix = """You are Marvin the socks seller, a poetic vendor of socks.
You are an expert in socks, and you reply with exactly one rhyme.
"""
    return prefix
```
</details>

<details>
    <summary>
        Tools
    </summary>

```python
from cat.mad_hatter.decorators import tool


# langchain inspired tools (function calling)
@tool(return_direct=True)
def socks_prices(color, cat):
    """How much do socks cost? Input is the sock color."""
    prices = {
        "black": 5,
        "white": 10,
        "pink": 50,
    }

    price = prices.get(color, 0)
    return f"{price} bucks, meeeow!" 
```
</details>

<details>
    <summary>
        Conversational Forms
    </summary>

```python
from enum import Enum
from pydantic import BaseModel, Field

from cat.mad_hatter.decorators import CatForm, form


class PizzaBorderEnum(Enum):
    HIGH = "high"
    LOW = "low"


# simple pydantic model
class PizzaOrder(BaseModel):
    pizza_type: str
    pizza_border: PizzaBorderEnum
    phone: str = Field(max_length=10)


@form
class PizzaForm(CatForm):
    name = "pizza_order"
    description = "Pizza Order"
    model_class = PizzaOrder
    examples = ["order a pizza", "I want pizza"]
    stop_examples = [
        "stop pizza order",
        "I do not want a pizza anymore",
    ]

    ask_confirm: bool = True

    def submit(self, form_data) -> str:
        return f"Form submitted: {form_data}"
```
</details>

<details>
    <summary>
        MCP Clients
    </summary>

```python
from typing import Dict, Any, List

from cat.mad_hatter.decorators import CatMcpClient, mcp_client

@mcp_client
class SampleMcpClient(CatMcpClient):
    """
    Sample MCP Client for testing purposes.
    """
    name = "sample_mcp_client"
    description = "Sample MCP Client"

    @property
    def init_args(self) -> List | Dict[str, Any]:
        pass
```
</details>

# Docs and Resources

**For your PHP based projects**, I developed a [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk) that allows you to
easily interact with the Cat. Please, refer to the [SDK documentation](https://www.github.com/matteocacciola/cheshirecat-php-sdk/blob/master/README.md) for more information.

**For your Node.js / React.js / Vue.js based projects**, I developed a [Typescript library](https://www.github.com/matteocacciola/cheshirecat-typescript-client) that allows you to
easily interact with the Cheshire Cat. Please, refer to the [library documentation](https://www.github.com/matteocacciola/cheshirecat-typescript-client/blob/master/README.md) for more information.

List of resources:
- [Official Documentation](https://deepwiki.com/matteocacciola/cheshirecat-core)
- [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk)
- [Typescript SDK](https://www.github.com/matteocacciola/cheshirecat-typescript-client)
- [Python SDK](https://www.github.com/matteocacciola/cheshirecat-python-sdk)
- [Tutorial - Write your first plugin](https://cheshirecat.ai/write-your-first-plugin/)

# Roadmap & Contributing

All contributions are welcome! Fork the project, create a branch, and make your changes.
Then, follow the [contribution guidelines](CONTRIBUTING.md) to submit your pull request.

If you like this fork, give it a star ⭐! It is very important to have your support. Thanks again!🙏

# License and trademark

Code is licensed under [GPL3](LICENSE).  
The Cheshire Cat AI logo and name are property of Piero Savastano (founder and maintainer). The current fork is created,
refactored and maintained by [Matteo Cacciola](mailto:matteo.cacciola@gmail.com).
