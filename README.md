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

- 🤖 Build your own AI agent in minutes, not months
- 🧠 Make it smart with Retrieval Augmented Generation (RAG)
- 🏆 Multi-modality, to build the RAG with any kind of documents
- 💬 Multi-tenancy, to manage multiple chatbots at the same time, each with its own settings, plugins, LLMs, etc.
- ⚡️ API first, to easily add a conversational layer to your app
- ☁️ Cloud Ready, working even with horizontal autoscaling
- 🔐 Secure by design, with API Key and granular permissions
- 🏗 Production ready, cloud native, and scalable
- 🐋 100% dockerized, to run anywhere
- 🛠 Easily extendable with plugins
- 🧩 Built-in plugins
  - 🪛 Extend core components (file managers, LLMs, vector databases)
  - ✂️ Customizable chunking and embedding
  - 🛠 Custom tools, forms, endpoints, MCP clients
  - 🪛 LLM callbacks
- 🌐 Customizable integration of **MCP clients**, such as LangSmith or LlamaIndex 
- 🏛 Easy to use Admin Panel (available with the repository [matteocacciola/cheshirecat-admin](https://www.github.com/matteocacciola/cheshirecat-admin))
- 🦄 Easy to understand [docs](https://deepwiki.com/matteocacciola/cheshirecat-core)
- 🌍 Supports any language model via LangChain

We are committed to openness, privacy and creativity, we want to bring AI to the long tail. If you want to know more
about our vision and values, read the [Code of Ethics](CODE-OF-ETHICS.md).

# Key differences of this version
The current version is a multi-tenant fork of the original [Cheshire Cat](https://www.github.com/cheshire-cat-ai/core).
The main differences are reported in the [CHANGELOG](CHANGELOG.md).

# Quickstart
To make Cheshire Cat run on your machine, you just need [`docker`](https://docs.docker.com/get-docker/) installed:

```bash
docker run --rm -it -p 1865:80 ghcr.io/matteocacciola/cheshirecat-core:latest
```
- Chat with the Cheshire Cat by downloading the [Admin Panel](https://www.github.com/matteocacciola/cheshirecat-admin) or by using the
  [widget](https://www.github.com/matteocacciola/cheshirecat-widget-vue).
- Try out the REST API on [localhost:1865/docs](http://localhost:1865/docs).

This fork is intended as a microservice.

As a first thing, set the **Embedder** for the Cheshire Cat. A favourite **LLM** must be set for each chatbot; each
chatbot can have its own language model, with custom settings.
Everything can be done via the [Admin Panel](https://www.github.com/matteocacciola/cheshirecat-admin) or via the REST API endpoints.

> [!IMPORTANT]
> The following `core plugins` are enabled by default:
> - `Conversation History`: to store and retrieve the conversation history;
> - `Factories`: extending objects like LLMs, Embedders, File Managers, Chunkers;
> - `Interactions`: add the interaction handler to the language model;
> - `March Hare`: handling events via RabbitMQ;
> - `Memory`: interacting with Working Memory and adding a handler to trace the activities of the Embedder;
> - `Multimodality`: a plugin that adds multimodal capabilities to the Cheshire Cat framework, enabling the processing of images;
> - `White Rabbit`: cron and schedule tasks;
> - `Why`: add the context and the reasoning behind the answers of the LLM.
> - `Analytics`: recover the analytics data about the usage of the Cheshire Cat, which depends on the `Interactions` and `Memory` plugins.
>
> You can disable one or more (e.g., `March Hare` if you don't need to autoscale over cloud PODs) by using the Admin Toggle endpoint.

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

# Compatibility 
This new version is no more completely compatible with the original version, since the architecture has been changed.
Please, refer to [COMPATIBILITY.md](COMPATIBILITY.md) for more information.

# Best practices

## Custom endpoints and permissions

When implementing custom endpoints, you can use the `@endpoint` decorator to create a new endpoint. Please, refer to the
[documentation](https://deepwiki.com/matteocacciola/cheshirecat-core) for more information.

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
from cat import hook


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
from cat import tool


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

from cat import CatForm, form


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
from cat import hook, log, mcp_client, plugin, CatMcpClient


# 1. Define your MCP client
@mcp_client
class WeatherMcpClient(CatMcpClient):
    """MCP client for weather information"""
    
    @property
    def init_args(self):
        # Return the connection parameters for your MCP server
        return {
            "server_url": "http://localhost:3000",
            # or for stdio: ["python", "path/to/mcp_server.py"]
        }


# 2. Hook to intercept elicitation requests and ask the user
@hook
def agent_fast_reply(fast_reply, cat):
    """
    Intercept tool responses that require elicitation.
    This hook runs after tools are executed but before the agent generates a response.
    """
    
    # Check if a tool returned an elicitation request
    if isinstance(fast_reply, dict) and fast_reply.get("status") == "elicitation_required":
        # Extract information about what we need
        field_description = fast_reply["message"]
        
        log.info(f"Elicitation required: {field_description}")
        
        # Return a message asking the user for the information
        # This will be sent to the user instead of going through the LLM
        return field_description
    
    # If not an elicitation, continue normally
    return fast_reply


# 3. Hook to capture user responses and store them
@hook
def before_agent_starts(agent_input, cat):
    """
    Handle user responses to pending elicitations.
    This hook runs at the start of each conversation turn.
    """
    
    # Check if there's a pending elicitation in working memory
    pending_elicitation = cat.working_memory.get("pending_mcp_elicitation")
    
    if pending_elicitation:
        log.info("Processing user response to pending elicitation")
        
        # Extract elicitation details
        mcp_client_name = pending_elicitation["mcp_client_name"]
        elicitation_id = pending_elicitation["elicitation_id"]
        missing_fields = pending_elicitation["missing_fields"]

        # Find the MCP client instance from plugin procedures
        client = None
        for procedure in cat.plugin_manager.procedures:
            if procedure.name == mcp_client_name:
                client = procedure
                break
        
        if client and missing_fields:
            # Get the first missing field (we handle one field per turn)
            first_field = missing_fields[0]
            field_name = first_field.get("name")
            
            # The user's input is their response to our question
            user_response = agent_input.input
            
            # Store the response
            client.store_elicitation_response(
                elicitation_id=elicitation_id,
                field_name=field_name,
                value=user_response,
                stray=cat
            )
            
            # Clear the pending elicitation
            del cat.working_memory["pending_mcp_elicitation"]
            
            log.info(f"Stored response for field '{field_name}': {user_response}")
            
            # Modify the input to tell the agent to retry the original tool
            # This ensures the agent knows to call the tool again
            original_tool_call = pending_elicitation.get("original_tool_call", "the original action")
            agent_input.input = f"I've just provided the required information: '{user_response}'. Please **retry the original tool call**: {original_tool_call}"

    return agent_input


# 4. (Optional) Hook to track which tool was being called
@hook
def before_cat_sends_message(message, cat):
    """
    You can use this to clean up or track state.
    """
    # Clean up any stale elicitation data if needed
    # (Usually not necessary as it's handled in before_agent_starts)
    return message


# 5. (Optional) Settings for your plugin
@plugin
def settings_schema():
    return {
        "mcp_server_url": {
            "title": "MCP Server URL",
            "type": "string",
            "default": "http://localhost:3000"
        }
    }
```
</details>

> [!IMPORTANT]
> A new feature has been added to the plugins of the Cheshire Cat: the possibility to **list the dependencies on other plugins**. This feature allows specifying that a plugin requires other plugins to be installed to work properly. This feature is optional, but it is recommended to use it to avoid issues with missing dependencies. To specify the dependencies of a plugin, you can use the `dependencies` attribute in the `plugin.json` file, listing the names of the plugins that the current plugin requires.

# Docs and Resources

**For your PHP based projects**, I developed a [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk) that allows you to
easily interact with the Cat. Please, refer to the [SDK documentation](https://www.github.com/matteocacciola/cheshirecat-php-sdk/blob/master/README.md) for more information.

**For your Node.js / React.js / Vue.js based projects**, I developed a [Typescript library](https://www.github.com/matteocacciola/cheshirecat-typescript-client) that allows you to
easily interact with the Cheshire Cat. Please, refer to the [library documentation](https://www.github.com/matteocacciola/cheshirecat-typescript-client/blob/master/README.md) for more information.

List of resources:
- [Official Documentation](https://deepwiki.com/matteocacciola/cheshirecat-core) of the current fork
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
