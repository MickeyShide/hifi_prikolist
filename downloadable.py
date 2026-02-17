import aiohttp
from dataclasses import dataclass
from typing import Callable, Any

@dataclass(slots=True)
class Downloadable:
    session: aiohttp.ClientSession
    url: str
    extension: str
    source: str = "tidal"

    async def download(self, path: str, callback: Callable[[int], Any]):
        await self._download(path, callback)

    async def _download(self, path: str, callback):
        async with self.session.get(self.url) as resp:
            resp.raise_for_status()
            with open(path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
                    callback(len(chunk))

    async def size(self) -> int:
        async with self.session.head(self.url) as response:
            content_length = response.headers.get("Content-Length", 0)
            return int(content_length)