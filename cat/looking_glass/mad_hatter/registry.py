import random
from typing import List
import aiofiles
import httpx

from cat.log import log
from cat.looking_glass.mad_hatter.plugin_manifest import PluginManifest


def get_registry_url():
    return "https://registry.cheshirecat.ai"


async def registry_search_plugins(
    query: str = None,
    # author: str = None,
    # tag: str = None,
) -> List[PluginManifest]:
    registry_url = get_registry_url()
    plugins = []

    try:
        if query:
            # search plugins
            url = f"{registry_url}/search"
            payload = {"query": query}

            async with httpx.AsyncClient() as client:
                plugins = (await client.post(url, json=payload)).json()
        else:
            # list plugins (no search)
            url = f"{registry_url}/plugins"
            params = {
                "page": 1,
                "page_size": 1000,
            }
            async with httpx.AsyncClient() as client:
                plugins = (await client.get(url, params=params)).json()["plugins"]
    except Exception:
        log.error("Error while calling plugins registry")
        return []

    manifests = []
    for r in plugins:
        r["id"] = r["url"]
        manifests.append(
            PluginManifest(**r)
        )
    # TODO: registry should sort plugins by score, until then we sort here at random
    random.shuffle(manifests)
    return manifests


async def registry_download_plugin(url: str) -> str:
    log.info(f"Downloading {url}")

    registry_url = get_registry_url()
    payload = {"url": url}

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{registry_url}/download", json=payload)
        response.raise_for_status()

        plugin_zip_path = f"/tmp/{url.split('/')[-1]}.zip"

        async with aiofiles.open(plugin_zip_path, "wb") as f:
            await f.write(response.content)  # Write the content asynchronously

    log.info(f"Saved plugin as {plugin_zip_path}")
    return plugin_zip_path
