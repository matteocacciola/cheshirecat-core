import random
from typing import List
import httpx

from cat import PluginRegistry
from cat.log import log
from cat.looking_glass.models import PluginManifest
from cat.utils import write_temp_file


class CheshireCatPluginRegistry(PluginRegistry):
    @property
    def registry_url(self) :
        return "https://registry.cheshirecat.ai"

    async def search_plugins(self, query: str = None) -> List[PluginManifest]:
        plugins = []
        try:
            if query:
                # search plugins
                url = f"{self.registry_url}/search"
                payload = {"query": query}

                async with httpx.AsyncClient() as client:
                    plugins = (await client.post(url, json=payload)).json()
            else:
                # list plugins (no search)
                url = f"{self.registry_url}/plugins"
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
            manifests.append(PluginManifest(**r))
        # TODO: registry should sort plugins by score, until then we sort here at random
        random.shuffle(manifests)
        return manifests

    async def download_plugin(self, url: str) -> str:
        log.info(f"Downloading {url}")

        payload = {"url": url}
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.registry_url}/download", json=payload)
            response.raise_for_status()
            plugin_zip_path = await write_temp_file(f"{url.split('/')[-1]}.zip", response.content)

        log.info(f"Saved plugin as {plugin_zip_path}")
        return plugin_zip_path
