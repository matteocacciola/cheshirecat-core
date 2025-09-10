<a name="readme-top"></a>

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h2>Cheshire Cat AI</h2>
  <h3>🇮🇹 Stregatto - 🇨🇳 柴郡貓 - 🇮🇳 चेशायर बिल्ली - 🇷🇺 Чеширский кот</h3>
<br/>
  <a href="https://www.github.com/matteocacciola/cheshirecat-core">
  <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/matteocacciola/cheshirecat-core?style=social">
</a>
  <a href="https://discord.gg/bHX5sNFCYU">
        <img src="https://img.shields.io/discord/1092359754917089350?logo=discord"
            alt="chat on Discord"></a>
  <a href="https://www.github.com/matteocacciola/cheshirecat-core/issues">
  <img alt="GitHub issues" src="https://img.shields.io/github/issues/matteocacciola/cheshirecat-core">
  </a>
  <a href="https://www.github.com/matteocacciola/cheshirecat-core/tags">
  <img alt="GitHub tag (with filter)" src="https://img.shields.io/github/v/tag/matteocacciola/cheshirecat-core">
  </a>
  <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/matteocacciola/cheshirecat-core">
</div>

# AI agent as a microservice

## Why use the Cat
The Cheshire Cat is a framework to build custom AI agents:

- ⚡️ API first, to easily add a conversational layer to your app
- 💬 Chat via WebSocket and manage your agent with an customizable REST API
- 🐘 Built-in RAG with **customizable vector database**, so you can use your own technology (e.g., Qdrant, Pinecone, Weaviate, etc.)
- 🐘 Customizable database for your documents, so that you can use your own storage (e.g., S3, MinIO, etc.)
- 🚀 Extensible via plugins
- 🪛 Event callbacks, function calling (tools), conversational forms
- 🏛 Easy to use Admin Panel (available with the repository [matteocacciola/cheshirecat-admin](https://www.github.com/matteocacciola/cheshirecat-admin))
- 🌍 Supports any language model via langchain
- 👥 Multiuser with granular permissions, compatible with any identity provider
- 💬 Multi-chatbots, with configurable (even different) LLM, chunking strategy and other features per chatbot, plus specific knowledge per chatbot
- 💬 Remembers conversations and documents and uses them in conversation
- ✂️ Customizable chunking and embedding
- ☁️ Cloud Ready, working even with horizontal autoscaling
- 🐋 100% dockerized
- 🦄 Active [Discord community](https://discord.gg/bHX5sNFCYU) and easy to understand [docs](https://cheshire-cat-ai.github.io/docs/)

We are committed to openness, privacy and creativity, we want to bring AI to the long tail. If you want to know more
about our vision and values, read the [Code of Ethics](CODE-OF-ETHICS.md).

# Key differences of this version
The current version is a multi-tenant fork of the original [Cheshire Cat](https://www.github.com/cheshire-cat-ai/core). Here are the main differences:

## Multitenancy
The original version was designed to be a single-tenant application, meaning that it could only manage one chatbot at a time.
This version is designed to be multi-tenant, meaning that it can manage multiple chatbots at the same time, each with its own settings, plugins, LLMs, etc.
**The way of "injecting" the identification of the Chatbot (RAG) is simple**:
  - **in case of the HTTP API endpoints, use the `agent_id` key into the request headers or as a querystring parameter;**
  - **in case of the WebSocket API, use the `agent_id` into the URL, e.g., `/ws/{agent_id}`.**

## RAG Customization:
The original version used a fixed RAG implementation, meaning that it could only use a specific vector database and chunking strategy.
This version allows you to configure the RAG per chatbot, meaning that you can use your own vector database and chunking strategy.
- **The current version supports multiple vector databases**, such as Qdrant, Pinecone, Weaviate, etc.
- **The current version supports multiple chunking strategies**, such as text splitting or Semantic chunking.

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

## Cloud ready
This version can be deployed in a cluster environment. Whilst the original version stored the settings into
JSON files, **this version requires a Redis database** to store the settings, the conversation histories, the plugins and so
forth.

You can **configure the Redis database by environment variables**. The [`compose.yml`](./compose.yml) file is provided as an example. 
Hence, the current version is multi-tenant, meaning that you can manage multiple RAGs and other language models at the same time.

The Cat is still stateless, so it can be easily scaled.  In case of a cluster environment, we suggest to use a shared storage,
mounted in the `cat/plugins` folder, to share the plugins.

A **RabbitMQ message broker** is recommended in a cluster environment, so that the installation
of plugins can be synchronized along all the PODs and the management of the Cat can be done in a distributed way. Its
configuration is done via environment variables, too. The [`compose.yml`](./compose.yml) file is provided as an example.

## Security
The original project is developed as a framework that could be used for a personal use as well as for single-tenant production.
In the latter case, the original [documentation](https://cheshire-cat-ai.github.io/docs/) clearly states to set up a secure environment
by using an API Key. **If not configured properly (e.g. by setting up an API Key), the current version will not work, indeed**.
In this way, I tried to make the Cat more secure and production-ready.

## Additional implementations
Here, the structure used for configuring `Embedder`, `LLMs`, `Authorization Handler`, `File Manager`, `Chunking Strategy`
and `Vector Database` has been changed: interfaces and factories have been used for the scope, in order to optimize the code and to allow
the extension of the list of allowed implementations. This way, you can use your own implementations of these components, if you want to.

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

## Compatibility with plugins
This new version is completely compatible with the original version, so you can easily migrate your existing plugins
and settings to the new version. It is still in development, but you can already try it out by running the Docker image.
New features will be added in the future. Please contact us if you want to contribute.

The list of available hooks are available in the [documentation](https://cheshire-cat-ai.github.io/docs/plugins/plugins/).

## List of available hooks
The Cat provides a set of hooks that can be used to customize the behavior of the AI agent. Hooks are events that can be
triggered at specific points in the conversation, allowing you to modify the behavior of the AI agent or to add custom functionality.
The list of available hooks is available in the [documentation](https://cheshire-cat-ai.github.io/docs/plugins/plugins/).
The current version introduces also the following additional hooks:

### Factories:
  - `factory_allowed_file_managers`: to extend the list of allowed file managers
  - `factory_allowed_chunkers`: to extend the list of allowed chunkers
  - `factory_allowed_vector_databases`: to extend the list of allowed vector databases (so allowing to use your own vector database)

# Quickstart
To make Cheshire Cat run on your machine, you just need [`docker`](https://docs.docker.com/get-docker/) installed:

```bash
docker run --rm -it -p 1865:80 ghcr.io/matteocacciola/cheshirecat-core:latest
```
- Chat with the Cheshire Cat on [localhost:1865/docs](http://localhost:1865/docs).

Since this version is intended as a microservice, the `admin` panel is no longer automatically installed with the package.

As a first thing, set the **Embedder** for the Cat. A favourite **LLM** must be set for each chatbot; each chatbot can have
its own language model, with custom settings.
Everything can be done via the [Admin Panel](https://www.github.com/matteocacciola/cheshirecat-admin) or via the REST API endpoints.

Enjoy the Cat!  
Follow instructions on how to run it with [docker compose and volumes](https://cheshire-cat-ai.github.io/docs/quickstart/installation-configuration/).

# Admin panel and UI widget
You can install an admin panel by using the [`cheshirecat-admin`](https://www.github.com/matteocacciola/cheshirecat-admin) repository.
The admin panel is a separate project that allows you to manage the Cat and its settings, plugins, and chatbots.
It is built with Streamlit and is designed to be easy to use and customizable.

Moreover, a suitable widget for the current fork is available in [my Github account](https://github.com/matteocacciola/cheshirecat-widget-vue)
to chat the Cat.

# API Usage

## For Streaming Responses (Real-time chat)
- **Use WebSocket connection** at `/ws`
- Receive tokens in real-time as they're generated
- Message type: `chat_token` for individual tokens
- Message type: `chat` for complete responses

## For Non-Streaming Responses (Simple API calls)
- **Use HTTP POST** to `/message`
- Receive complete response in single API call
- Better for integrations, batch processing, or simple request/response patterns

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
from pydantic import BaseModel
from cat.experimental.form import form, CatForm

# data structure to fill up
class PizzaOrder(BaseModel):
    pizza_type: str
    phone: int

# forms let you control goal oriented conversations
@form
class PizzaForm(CatForm):
    description = "Pizza Order"
    model_class = PizzaOrder
    start_examples = [
        "order a pizza!",
        "I want pizza"
    ]
    stop_examples = [
        "stop pizza order",
        "not hungry anymore",
    ]
    ask_confirm = True

    def submit(self, form_data):
        # do the actual order here!

        # return to convo
        return {
            "output": f"Pizza order on its way: {form_data}"
        }
```
</details>

# Docs and Resources

**For your PHP based projects**, I developed a [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk) that allows you to
easily interact with the Cat. Please, refer to the [SDK documentation](https://www.github.com/matteocacciola/cheshirecat-php-sdk/blob/master/README.md) for more information.

**For your Node.js / React.js / Vue.js based projects**, I developed a [Typescript library](https://www.github.com/matteocacciola/cheshirecat-nodejs-sdk) that allows you to
easily interact with the Cat. Please, refer to the [library documentation](https://www.github.com/matteocacciola/cheshirecat-nodejs-sdk/blob/master/README.md) for more information.

List of resources:
- [Official Documentation](https://cheshire-cat-ai.github.io/docs/)
- [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk)
- [Typescript SDK](https://www.github.com/matteocacciola/cheshirecat-typescript-client)
- [Python SDK](https://www.github.com/matteocacciola/cheshirecat-python-sdk)
- [Discord Server](https://discord.gg/bHX5sNFCYU)
- [Website](https://cheshirecat.ai/)
- [Tutorial - Write your first plugin](https://cheshirecat.ai/write-your-first-plugin/)

# Roadmap & Contributing

All contributions are welcome! Fork the project, create a branch, and make your changes.
Then, follow the [contribution guidelines](CONTRIBUTING.md) to submit your pull request.

If you like this fork, give it a star ⭐! It is very important to have your support. Thanks again!🙏

# License and trademark

Code is licensed under [GPL3](LICENSE).  
The Cheshire Cat AI logo and name are property of Piero Savastano (founder and maintainer). The current fork is created,
refactored and maintained by [Matteo Cacciola](mailto:matteo.cacciola@gmail.com).
