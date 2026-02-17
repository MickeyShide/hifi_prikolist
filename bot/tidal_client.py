import aiohttp
import base64
import json
import time
import asyncio
import os
from typing import Optional

BASE = "https://api.tidalhifi.com/v1"
AUTH_URL = "https://auth.tidal.com/v1/oauth2"

CLIENT_ID = base64.b64decode("ZlgySnhkbW50WldLMGl4VA==").decode("iso-8859-1")
CLIENT_SECRET = base64.b64decode(
    "MU5tNUFmREFqeHJnSkZKYktOV0xlQXlLR1ZHbUlOdVhQUExIVlhBdnhBZz0=",
).decode("iso-8859-1")

QUALITY_MAP = {
    0: "LOW",   # AAC
    1: "HIGH",  # AAC
    2: "LOSSLESS",  # CD Quality FLAC
    3: "HI_RES",  # MQA FLAC
}

class TidalAuth:
    """Handles Tidal authentication with token persistence."""
    
    def __init__(self, config):
        self.config = config
        self.session = None
        self.tokens = config.load_tokens()
        
    async def _create_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def is_token_valid(self) -> bool:
        """Check if access token is still valid."""
        if not self.tokens.access_token:
            return False
            
        # Check if token expired (with 1 hour buffer)
        if time.time() > (self.tokens.token_expiry - 3600):
            return False
            
        return True
        
    async def refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        if not self.tokens.refresh_token:
            return False
            
        await self._create_session()
        
        data = {
            "client_id": CLIENT_ID,
            "refresh_token": self.tokens.refresh_token,
            "grant_type": "refresh_token",
            "scope": "r_usr+w_usr+w_sub",
        }
        
        try:
            async with self.session.post(f"{AUTH_URL}/token", data=data, 
                                       auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)) as resp:
                resp_data = await resp.json()
                
            if "access_token" not in resp_data:
                print(f"Refresh failed: {resp_data}")
                return False
                
            # Update tokens
            self.tokens.access_token = resp_data["access_token"]
            self.tokens.refresh_token = resp_data["refresh_token"]
            self.tokens.token_expiry = resp_data["expires_in"] + time.time()
            self.tokens.user_id = resp_data["user"]["userId"]
            self.tokens.country_code = resp_data["user"]["countryCode"]
            
            # Save updated tokens
            self.config.save_tokens(self.tokens)
            print("Token refreshed successfully")
            return True
            
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return False
            
    async def device_login(self) -> bool:
        """Perform device login flow and save tokens."""
        await self._create_session()
        
        # Step 1: Get device code
        data = {"client_id": CLIENT_ID, "scope": "r_usr+w_usr+w_sub"}
        
        async with self.session.post(f"{AUTH_URL}/device_authorization", data=data) as resp:
            resp_data = await resp.json()
            
        device_code = resp_data["deviceCode"]
        verification_uri = resp_data["verificationUriComplete"]
        
        print(f"\n🔗 Please visit this URL in your browser:")
        print(f"👉 {verification_uri}")
        print("\n⏳ Waiting for authentication...")
        
        # Step 2: Poll for token
        data = {
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "scope": "r_usr+w_usr+w_sub",
        }
        
        # Poll for 10 minutes (150 attempts with 4 second intervals)
        for attempt in range(150):
            await asyncio.sleep(4)
            
            try:
                async with self.session.post(f"{AUTH_URL}/token", data=data, 
                                           auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)) as resp:
                    resp_data = await resp.json()
                    
                if "access_token" in resp_data:
                    # Save tokens
                    self.tokens.access_token = resp_data["access_token"]
                    self.tokens.refresh_token = resp_data["refresh_token"]
                    self.tokens.token_expiry = resp_data["expires_in"] + time.time()
                    self.tokens.user_id = resp_data["user"]["userId"]
                    self.tokens.country_code = resp_data["user"]["countryCode"]
                    
                    self.config.save_tokens(self.tokens)
                    print("✅ Authentication successful! Tokens saved.")
                    return True
                    
            except Exception as e:
                print(f"Attempt {attempt + 1}/150 failed: {e}")
                
        print("❌ Authentication timeout")
        return False
        
    async def ensure_login(self) -> bool:
        """Ensure we have valid authentication."""
        await self._create_session()
        
        # Check if we have valid token
        if await self.is_token_valid():
            # Set authorization header
            self.session.headers.update({
                "authorization": f"Bearer {self.tokens.access_token}"
            })
            return True
            
        # Try to refresh token
        print("Token expired or invalid, trying to refresh...")
        if await self.refresh_token():
            self.session.headers.update({
                "authorization": f"Bearer {self.tokens.access_token}"
            })
            return True
            
        # If refresh failed, need new device login
        print("Refresh failed, need new device login...")
        return False
        
    async def close(self):
        if self.session:
            await self.session.close()

class TidalClient:
    """Main Tidal client for downloading tracks."""
    
    def __init__(self, config):
        self.config = config
        self.auth = TidalAuth(config)
        self.session = None
        
    async def login(self) -> bool:
        """Login to Tidal (automatic token management)."""
        if await self.auth.ensure_login():
            self.session = self.auth.session
            return True
        return False
        
    async def get_track_info(self, track_id: str) -> Optional[dict]:
        """Get track information."""
        if not self.session:
            return None
            
        params = {
            "countryCode": self.auth.tokens.country_code,
            "limit": 100
        }
        
        try:
            async with self.session.get(f"{BASE}/tracks/{track_id}", params=params) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            print(f"Error getting track info: {e}")
            return None
            
    async def download_track(self, track_id: str, quality: Optional[int] = None) -> Optional[str]:
        """Download track and return file path."""
        if not self.session:
            return None
            
        if quality is None:
            quality = self.config.QUALITY
            
        quality_str = QUALITY_MAP.get(quality, "LOSSLESS")
        
        try:
            # Get download URL
            params = {
                "audioquality": quality_str,
                "playbackmode": "STREAM",
                "assetpresentation": "FULL",
                "countryCode": self.auth.tokens.country_code,
            }
            
            async with self.session.get(
                f"{BASE}/tracks/{track_id}/playbackinfopostpaywall", 
                params=params
            ) as resp:
                resp_data = await resp.json()
                
            if "manifest" not in resp_data:
                print(f"No manifest: {resp_data}")
                return None
                
            # Decode manifest
            manifest = json.loads(base64.b64decode(resp_data["manifest"]).decode("utf-8"))
            download_url = manifest["urls"][0]
            
            # Get track info for filename
            track_info = await self.get_track_info(track_id)
            if not track_info:
                print(f"Track {track_id} not found")
                return None
                
            # Create safe filename
            artist = track_info.get('artist', {}).get('name', 'Unknown Artist')
            title = track_info.get('title', 'Unknown Track')
            
            # Clean filename (remove invalid characters)
            def clean(text):
                keep_chars = (' ', '-', '_', '.', ',', '&', "'", '(', ')')
                return ''.join(c for c in text if c.isalnum() or c in keep_chars).strip()
                
            artist_clean = clean(artist)
            title_clean = clean(title)
            extension = "flac" if quality >= 2 else "m4a"
            
            # Truncate if too long
            max_length = 100
            filename = f"{artist_clean} - {title_clean}.{extension}"
            if len(filename) > max_length:
                filename = f"{artist_clean[:30]} - {title_clean[:50]}.{extension}"
                
            filepath = os.path.join(self.config.DOWNLOAD_FOLDER, filename)
            
            # If file already exists, return it
            if os.path.exists(filepath):
                print(f"File already exists: {filename}")
                return filepath
                
            # Download file
            print(f"Downloading: {artist} - {title}")
            async with self.session.get(download_url) as resp:
                resp.raise_for_status()
                
                total_size = int(resp.headers.get('content-length', 0))
                
                with open(filepath, 'wb') as f:
                    downloaded = 0
                    async for chunk in resp.content.iter_chunked(8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                print(f"Downloaded: {filename} ({downloaded} bytes)")
                
            return filepath
            
        except Exception as e:
            print(f"Error downloading track {track_id}: {e}")
            return None
            
    async def close(self):
        await self.auth.close()
        
    async def __aenter__(self):
        await self.login()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()