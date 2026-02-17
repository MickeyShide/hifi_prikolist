"""Minimal config for Tidal only."""

import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class TidalConfig:
    user_id: str = ""
    country_code: str = "US"
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: str = "0"
    quality: int = 2  # HiFi FLAC

@dataclass(slots=True)
class DownloadsConfig:
    folder: str = ""
    verify_ssl: bool = True
    requests_per_minute: int = 100

@dataclass(slots=True)
class Config:
    tidal: TidalConfig
    downloads: DownloadsConfig
    
    def __init__(self):
        HOME = Path.home()
        self.downloads = DownloadsConfig(
            folder=os.path.join(HOME, "StreamripDownloads")
        )
        self.tidal = TidalConfig()