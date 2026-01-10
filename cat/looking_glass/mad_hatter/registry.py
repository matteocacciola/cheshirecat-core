from abc import ABC, abstractmethod
from typing import List

from cat.looking_glass.mad_hatter.plugin_manifest import PluginManifest


class PluginRegistry(ABC):
    @property
    @abstractmethod
    def registry_url(self) -> str:
        """
        Returns the URL of the plugin registry.
        """
        pass

    @abstractmethod
    async def search_plugins(self, query: str = None) -> List[PluginManifest]:
        """
        Search for plugins in the registry.
        Args:
            query: The query to search for.

        Returns:
            List of PluginManifest objects.
        """
        pass

    @abstractmethod
    async def download_plugin(self, url: str) -> str:
        """
        Download a plugin from the registry.

        Args:
            url: The URL of the plugin to download.

        Returns:
            The path to the downloaded plugin zip file.
        """
        pass
