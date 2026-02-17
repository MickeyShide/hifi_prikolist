"""Base client interface."""

import aiohttp
from abc import ABC, abstractmethod

from downloadable import Downloadable

class Client(ABC):
    source: str
    max_quality: int
    session: aiohttp.ClientSession
    logged_in: bool = False

    @abstractmethod
    async def login(self):
        raise NotImplementedError

    @abstractmethod
    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def get_downloadable(self, item_id: str, quality: int) -> Downloadable:
        raise NotImplementedError