import asyncio
import base64
import json
import time
import aiohttp

from config import Config
from client import Client
from downloadable import Downloadable
from exceptions import AuthenticationError, NonStreamableError

BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = base64.b64decode("ZlgySnhkbW50WldLMGl4VA==").decode("iso-8859-1")
CLIENT_SECRET = base64.b64decode(
    "MU5tNUFmREFqeHJnSkZKYktOV0xlQXlLR1ZHbUlOdVhQUExIVlhBdnhBZz0=",
).decode("iso-8859-1")
AUTH = aiohttp.BasicAuth(login=CLIENT_ID, password=CLIENT_SECRET)

QUALITY_MAP = {
    0: "LOW",   # AAC
    1: "HIGH",  # AAC
    2: "LOSSLESS",  # CD Quality
    3: "HI_RES",  # MQA
}

class TidalClient(Client):
    source = "tidal"
    max_quality = 3

    def __init__(self, config: Config):
        self.config = config
        self.session = None
        self.logged_in = False

    async def login(self):
        """Login using device flow."""
        self.session = aiohttp.ClientSession()
        
        if not self.config.tidal.access_token:
            await self._device_login()
        else:
            await self._login_by_access_token()
        
        self.logged_in = True

    async def _device_login(self):
        """Login using device code flow."""
        data = {"client_id": CLIENT_ID, "scope": "r_usr+w_usr+w_sub"}
        
        async with self.session.post(f"{AUTH_URL}/device_authorization", data=data) as resp:
            resp_data = await resp.json()
        
        device_code = resp_data["deviceCode"]
        verification_uri = resp_data["verificationUriComplete"]
        
        print(f"Please visit: {verification_uri}")
        print("Waiting for authentication...")
        
        data = {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        
        # Poll for authentication
        for _ in range(150):  # 10 minutes
            await asyncio.sleep(4)
            
            async with self.session.post(f"{AUTH_URL}/token", data=data, auth=AUTH) as resp:
                resp_data = await resp.json()
            
            if "access_token" in resp_data:
                self.config.tidal.access_token = resp_data["access_token"]
                self.config.tidal.refresh_token = resp_data["refresh_token"]
                self.config.tidal.token_expiry = str(resp_data["expires_in"] + time.time())
                self.config.tidal.user_id = resp_data["user"]["userId"]
                self.config.tidal.country_code = resp_data["user"]["countryCode"]
                
                self.session.headers.update({
                    "authorization": f"Bearer {self.config.tidal.access_token}"
                })
                return
        
        raise AuthenticationError("Authentication timeout")

    async def _login_by_access_token(self):
        """Login using stored access token."""
        self.session.headers.update({
            "authorization": f"Bearer {self.config.tidal.access_token}"
        })
        
        # Verify token is still valid
        async with self.session.get("https://api.tidal.com/v1/sessions") as resp:
            resp_data = await resp.json()
        
        if resp_data.get("status", 200) != 200:
            raise AuthenticationError("Invalid access token")

    async def get_metadata(self, item_id: str, media_type: str) -> dict:
        """Get track metadata."""
        params = {
            "countryCode": self.config.tidal.country_code,
            "limit": 100
        }
        
        async with self.session.get(f"{BASE}/tracks/{item_id}", params=params) as resp:
            if resp.status == 404:
                raise NonStreamableError("Track not found")
            resp.raise_for_status()
            return await resp.json()

    async def get_downloadable(self, track_id: str, quality: int):
        """Get downloadable track URL."""
        params = {
            "audioquality": QUALITY_MAP[quality],
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
            "countryCode": self.config.tidal.country_code,
        }
        
        async with self.session.get(
            f"{BASE}/tracks/{track_id}/playbackinfopostpaywall", 
            params=params
        ) as resp:
            resp_data = await resp.json()
        
        try:
            manifest = json.loads(base64.b64decode(resp_data["manifest"]).decode("utf-8"))
        except KeyError:
            raise Exception(resp_data.get("userMessage", "Unknown error"))
        
        return Downloadable(
            self.session,
            url=manifest["urls"][0],
            extension="flac" if quality >= 2 else "m4a",
            source="tidal"
        )