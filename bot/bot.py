import asyncio
import os
import logging
from pathlib import Path
import re

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from config import Config
from tidal import BASE
from tidal_client import TidalClient, TidalAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize config and bot
config = Config()
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Global tidal client instance
tidal_client = None

def is_valid_track_id(text: str) -> bool:
    """Check if text is a valid Tidal track ID (numeric)."""
    return text.isdigit() and len(text) >= 6

async def startup():
    """Initialize Tidal client on startup."""
    global tidal_client
    
    tidal_client = TidalClient(config)
    
    # Try to login with saved tokens
    if await tidal_client.login():
        logger.info("✅ Tidal client logged in with saved tokens")
    else:
        logger.warning("❌ No valid tokens found. Use /login command to authenticate.")
        
    # Send startup notification to admin
    if config.ADMIN_ID:
        try:
            await bot.send_message(config.ADMIN_ID, "🤖 Bot started successfully")
        except:
            pass

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Start command handler."""
    if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Access denied")
        return
        
    await message.answer(
        "🎵 Tidal Download Bot\n\n"
        "Send me a Tidal track ID (numbers only) and I'll download it for you.\n\n"
        "Commands:\n"
        "/login - Login to Tidal (device flow)\n"
        "/status - Check Tidal connection\n"
        "/clean - Clean download folder"
    )

@dp.message(Command("login"))
async def cmd_login(message: Message):
    """Initiate Tidal login."""
    if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Access denied")
        return
        
    await message.answer("Starting Tidal authentication...")
    
    # Create auth instance
    auth = TidalAuth(config)
    
    # Start device login
    msg = await message.answer("Please check bot logs for login URL...")
    
    # Run login in background
    success = await auth.device_login()
    
    if success:
        await msg.edit_text("✅ Login successful! Tokens saved.\nYou can now download tracks.")
        
        # Reinitialize client with new tokens
        global tidal_client
        tidal_client = TidalClient(config)
        await tidal_client.login()
    else:
        await msg.edit_text("❌ Login failed. Please try again.")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Check Tidal connection status."""
    if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Access denied")
        return
        
    global tidal_client
    
    if not tidal_client or not tidal_client.session:
        await message.answer("❌ Tidal client not initialized")
        return
        
    # Check connection
    try:
        # Simple API call to check connection
        params = {"countryCode": "US", "limit": 1}
        async with tidal_client.session.get(f"{BASE}/tracks/123", params=params) as resp:
            status = resp.status
            
        if status == 401:
            await message.answer("⚠️ Tidal token expired. Use /login to refresh.")
        elif status == 200 or status == 404:
            await message.answer("✅ Tidal connection is working")
        else:
            await message.answer(f"⚠️ Tidal status: {status}")
            
    except Exception as e:
        await message.answer(f"❌ Tidal error: {str(e)}")

@dp.message(Command("clean"))
async def cmd_clean(message: Message):
    """Clean download folder."""
    if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Access denied")
        return
        
    try:
        # Remove all files in download folder
        for file in os.listdir(config.DOWNLOAD_FOLDER):
            file_path = os.path.join(config.DOWNLOAD_FOLDER, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                
        await message.answer(f"🧹 Cleaned {config.DOWNLOAD_FOLDER} folder")
    except Exception as e:
        await message.answer(f"❌ Error cleaning: {str(e)}")

@dp.message()
async def handle_track_id(message: Message):
    """Handle track ID messages."""
    # Check if user is admin
    #if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        #return
        
    track_id = message.text.strip()
    
    # Validate track ID
    if not is_valid_track_id(track_id):
        # Not a valid track ID, ignore
        return
        
    # Check if client is ready
    global tidal_client
    if not tidal_client or not tidal_client.session:
        await message.answer("❌ Tidal client not ready. Use /login first.")
        return
        
    # Send processing message
    status_msg = await message.answer(f"🔍 Processing track ID: {track_id}")
    
    try:
        # Get track info first
        track_info = await tidal_client.get_track_info(track_id)
        if not track_info:
            await status_msg.edit_text(f"❌ Track {track_id} not found")
            return
            
        artist = track_info.get('artist', {}).get('name', 'Unknown Artist')
        title = track_info.get('title', 'Unknown Track')
        
        await status_msg.edit_text(f"⬇️ Downloading: {artist} - {title}")
        
        # Download track
        filepath = await tidal_client.download_track(track_id)
        
        if not filepath or not os.path.exists(filepath):
            await status_msg.edit_text(f"❌ Failed to download track {track_id}")
            return
            
        # Send file
        await status_msg.edit_text(f"📤 Sending file...")
        
        # Create FSInputFile
        audio_file = FSInputFile(filepath)
        
        # Send as audio with caption
        await message.answer_audio(
            audio=audio_file,
            caption=f"{artist} - {title}",
            title=title,
            performer=artist
        )
        
        await status_msg.delete()
        
        # Clean up file after sending (optional)
        # os.remove(filepath)
        
    except Exception as e:
        logger.error(f"Error processing track {track_id}: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def main():
    """Main function."""
    await startup()
    
    # Start polling
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())