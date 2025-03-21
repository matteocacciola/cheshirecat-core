<a name="readme-top"></a>

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h2>Cheshire Cat AI</h2>
  <h3>🇮🇹 Stregatto - 🇨🇳 柴郡貓 - 🇮🇳 चेशायर बिल्ली - 🇷🇺 Чеширский кот</h3>
<br/>
  <a href="https://github.com/matteocacciola/cheshirecat-core">
  <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/matteocacciola/cheshirecat-core?style=social">
</a>
  <a href="https://discord.gg/bHX5sNFCYU">
        <img src="https://img.shields.io/discord/1092359754917089350?logo=discord"
            alt="chat on Discord"></a>
  <a href="https://github.com/matteocacciola/cheshirecat-core/issues">
  <img alt="GitHub issues" src="https://img.shields.io/github/issues/matteocacciola/cheshirecat-core">
  </a>
  <a href="https://github.com/matteocacciola/cheshirecat-core/tags">
  <img alt="GitHub tag (with filter)" src="https://img.shields.io/github/v/tag/matteocacciola/cheshirecat-core">
  </a>
  <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/matteocacciola/cheshirecat-core">
</div>

## AI agent as a microservice

The Cheshire Cat is a framework to build custom AI agents:

- ⚡️ API first, to easily add a conversational layer to your app
- 💬 Chat via WebSocket and manage your agent with an customizable REST API
- 🐘 Built-in RAG with Qdrant
- 🚀 Extensible via plugins
- 🪛 Event callbacks, function calling (tools), conversational forms
- 🏛 Easy to use admin panel
- 🌍 Supports any language model via langchain
- 👥 Multiuser with granular permissions, compatible with any identity provider
- 💬 Multi-chatbots, with configurable (even different) LLM per chatbot, plus specific knowledge per chatbot
- ☁️ Cloud Ready, working even with horizontal autoscaling
- 🐋 100% dockerized
- 🦄 Active [Discord community](https://discord.gg/bHX5sNFCYU) and easy to understand [docs](https://cheshire-cat-ai.github.io/docs/)

### Key differences

The current version is a multi-tenant fork of the original [Cheshire Cat](https://github.com/cheshire-cat-ai/core). Here are the main differences:

- **New features**: here, I have introduced some new features and improvements, such as:
  - The `Embedder` is centralized and can be used by multiple RAGs and other language models.
  - A new `File Manager` that allows you to store files, injected to the RAG, into a remote storage.
  - New admin endpoints allowing to configure the `Embedder` and `File Manager`.
  - A new event system that allows you to get fine-grained control over the AI.
  - **The ability to manage multiple RAGs and other language models at the same time**.
- **Customizable multi-chatbots**: the current version proposes a platform where each chatbot is fully customizable in terms of
plugjns, settings, LLM, etc.
**The way of "injecting" the identification of the Chatbot (RAG) is simple**:
  - **in case of the HTTP API endpoints, use the `agent_id` key into the request headers or as a querystring parameter;**
  - **in case of the WebSocket API, use the `agent_id` into the URL, e.g., `/ws/{agent_id}`.**
- **Cloud ready**: this version can be deployed in a cluster environment. Whilst the original version stored the settings into
JSON files, **this version requires a Redis database** to store the  settings, the conversation histories, the plugins and so
forth. You can **configure the Redis database by environment variables**. The [`compose.yml`](./compose.yml) file is provided as an example.
The Cat is still stateless, so it can be easily scaled.
In case of a cluster environment, we suggest to use a shared storage, mounted in the `cat/plugins` folder, to share the plugins.
Hence, the current version is multi-tenant, meaning that you can manage multiple RAGs and other language models at the same time.
- **Security**: the original project is developed as a framework that could be used for a personal use as well as for single-tenant production.
In the latter case, the original [documentation](https://cheshire-cat-ai.github.io/docs/) clearly states to set up a secure environment
by using an API Key. **If not configured properly (e.g. by setting up an API Key), the current version will not work, indeed**.
In this way, I tried to make the Cat more secure and production-ready.
- **Additional implementations**: here, the structure used for configuring `Embedder`, `LLMs`, `Authorization Handler` and `File Manager`
is different from the original version: interfaces and factories have been used for the scope.

## Compatibility with plugins

This new version is completely compatible with the original version, so you can easily migrate your existing plugins
and settings to the new version. It is still in development, but you can already try it out by running the Docker image.
New features will be added in the future. Please contact us if you want to contribute.

## Quickstart

To make Cheshire Cat run on your machine, you just need [`docker`](https://docs.docker.com/get-docker/) installed:

```bash
docker run --rm -it -p 1865:80 ghcr.io/matteocacciola/cheshirecat-core:2.0.6
```
- Chat with the Cheshire Cat on [localhost:1865/docs](http://localhost:1865/docs).

Since this version is intended as a microservice, the `admin` panel is no longer available. You can still use widgets from
the [original project](https://github.com/cheshire-cat-ai/) to manage the Cat.

As a first thing, the Cat will ask you to configure your favourite language model.
It can be done directly via the interface in the Settings page (top right in the admin).

Enjoy the Cat!  
Follow instructions on how to run it with [docker compose and volumes](https://cheshire-cat-ai.github.io/docs/quickstart/installation-configuration/).

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

## Docs and Resources

**For your PHP based projects**, I developed a [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk) that allows you to
easily interact with the Cat. Please, refer to the [SDK documentation](https://www.github.com/matteocacciola/cheshirecat-php-sdk/blob/master/README.md) for more information.

**For your Node.js based projects**, I developed a [Node.js SDK](https://www.github.com/matteocacciola/cheshirecat-nodejs-sdk) that allows you to
easily interact with the Cat. Please, refer to the [SDK documentation](https://www.github.com/matteocacciola/cheshirecat-nodejs-sdk/blob/master/README.md) for more information.

List of resources:
- [Official Documentation](https://cheshire-cat-ai.github.io/docs/)
- [PHP SDK](https://www.github.com/matteocacciola/cheshirecat-php-sdk)
- [Typescript SDK](https://www.github.com/matteocacciola/cheshirecat-typescript-client)
- [Python SDK](https://www.github.com/matteocacciola/cheshirecat-python-sdk)
- [Discord Server](https://discord.gg/bHX5sNFCYU)
- [Website](https://cheshirecat.ai/)
- [Tutorial - Write your first plugin](https://cheshirecat.ai/write-your-first-plugin/)

## Why use the Cat

- ⚡️ API first, so you get a microservice to easily add a conversational layer to your app
- 🐘 Remembers conversations and documents and uses them in conversation
- 🚀 Extensible via plugins (public plugin registry + private plugins allowed)
- 🎚 Event callbacks, function calling (tools), conversational forms
- 🏛 Easy to use admin panel (chat, visualize memory and plugins, adjust settings)
- 🌍 Supports any language model (works with OpenAI, Google, Ollama, HuggingFace, custom services)
- 💬 Multi-chatbots, with configurable (even different) LLM per chatbot, plus specific knowledge per chatbot
- ☁️ Cloud Ready, working even with horizontal autoscaling
- 🐋 Production ready - 100% [dockerized](https://docs.docker.com/get-docker/)
- 👩‍👧‍👦 Active [Discord community](https://discord.gg/bHX5sNFCYU) and easy to understand [docs](https://cheshire-cat-ai.github.io/docs/)
 
We are committed to openness, privacy and creativity, we want to bring AI to the long tail. If you want to know more
about our vision and values, read the [Code of Ethics](CODE-OF-ETHICS.md).

## Roadmap & Contributing

All contributions are welcome! Fork the project, create a branch, and make your changes.
Then, follow the [contribution guidelines](CONTRIBUTING.md) to submit your pull request.

If you like this project, give it a star ⭐! It is very important to have your support. Thanks again!🙏

## License and trademark

Code is licensed under [GPL3](LICENSE).  
The Cheshire Cat AI logo and name are property of Piero Savastano (founder and maintainer). The current fork is created,
refactored and maintained by [Matteo Cacciola](mailto:matteo.cacciola@gmail.com).

## Which way to go?

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<p align="center">
    <img align="center" src=./readme/cheshire-cat.jpeg width=400px alt="Wikipedia picture of the Cheshire Cat">
</p>

```
"Would you tell me, please, which way I ought to go from here?"
"That depends a good deal on where you want to get to," said the Cat.
"I don't much care where--" said Alice.
"Then it doesn't matter which way you go," said the Cat.

(Alice's Adventures in Wonderland - Lewis Carroll)

```
