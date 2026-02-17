import os
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKENS_FILE = "tidal_tokens.json"

@dataclass
class TidalTokens:
    access_token: str = ""
    refresh_token: str = ""
    user_id: str = ""
    country_code: str = "US"
    token_expiry: float = 0.0

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", 0))
    
    # Download settings
    DOWNLOAD_FOLDER: str = "downloads"
    QUALITY: int = 2  # 2 = FLAC
    
    def __post_init__(self):
        # Create downloads folder
        os.makedirs(self.DOWNLOAD_FOLDER, exist_ok=True)
        
    def save_tokens(self, tokens: TidalTokens):
        """Save tokens to file."""
        with open(TOKENS_FILE, 'w') as f:
            json.dump(asdict(tokens), f)
        print(f"Tokens saved to {TOKENS_FILE}")
        
    def load_tokens(self) -> TidalTokens:
        """Load tokens from file."""
        if os.path.exists(TOKENS_FILE):
            try:
                with open(TOKENS_FILE, 'r') as f:
                    data = json.load(f)
                    return TidalTokens(**data)
            except Exception as e:
                print(f"Error loading tokens: {e}")
        return TidalTokens()