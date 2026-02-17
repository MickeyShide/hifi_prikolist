"""Minimal CLI for downloading Tidal tracks by ID."""

import asyncio
import click
import os
from pathlib import Path
from config import Config
from tidal import TidalClient

@click.command()
@click.argument('track_id')
@click.option('--quality', '-q', type=int, default=2, help='Quality: 0=LOW, 1=HIGH, 2=LOSSLESS, 3=HI_RES')
@click.option('--output', '-o', type=click.Path(), help='Output directory')
def download_track(track_id, quality, output):
    """Download a Tidal track by ID."""
    asyncio.run(main(track_id, quality, output))

async def main(track_id, quality, output_dir):
    config = Config()
    
    if quality not in range(4):
        print(f"Invalid quality: {quality}. Must be 0-3")
        return
    
    config.tidal.quality = quality
    
    if output_dir:
        config.downloads.folder = output_dir
    
    # Ensure output directory exists
    os.makedirs(config.downloads.folder, exist_ok=True)
    
    client = TidalClient(config)
    
    try:
        print("Logging in to Tidal...")
        await client.login()
        
        print(f"Fetching track info for ID: {track_id}...")
        metadata = await client.get_metadata(track_id, "track")
        
        track_title = metadata.get('title', 'Unknown Track')
        artist = metadata.get('artist', {}).get('name', 'Unknown Artist')
        
        print(f"Track: {artist} - {track_title}")
        
        print("Getting download URL...")
        downloadable = await client.get_downloadable(track_id, quality)
        
        # Create filename
        safe_title = "".join(c for c in track_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_artist} - {safe_title}.{downloadable.extension}"
        filepath = os.path.join(config.downloads.folder, filename)
        
        print(f"Downloading to: {filepath}")
        
        # Simple progress callback
        total_size = await downloadable.size()
        downloaded = 0
        
        def progress_callback(chunk_size):
            nonlocal downloaded
            downloaded += chunk_size
            percent = (downloaded / total_size) * 100 if total_size > 0 else 0
            print(f"\rProgress: {downloaded}/{total_size} bytes ({percent:.1f}%)", end='')
        
        await downloadable.download(filepath, progress_callback)
        print(f"\nDownload complete: {filepath}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client.session:
            await client.session.close()

if __name__ == "__main__":
    download_track()