import subprocess
import os
import shutil
from pathlib import Path

def extract_mp3_advanced(mp4_file_path, mp3_output_path=None, **kwargs):
    """
    Advanced MP3 extraction with customizable options.
    
    Args:
        mp4_file_path (str): Path to input MP4 file
        mp3_output_path (str, optional): Path for output MP3 file
        **kwargs: Additional options:
            - bitrate (str): Audio bitrate (default: '192k')
            - sample_rate (str): Audio sample rate (default: '44100')
            - channels (str): Number of audio channels (default: '2')
            - start_time (str): Start time for extraction (e.g., '00:01:30')
            - duration (str): Duration to extract (e.g., '00:02:00')
            - quiet (bool): Suppress ffmpeg output (default: True)
    
    Returns:
        str: Path to the created MP3 file
    """
    # Default options
    options = {
        'bitrate': '192k',
        'sample_rate': '44100',
        'channels': '2',
        'quiet': True
    }
    options.update(kwargs)
    
    # Validate input
    if not os.path.exists(mp4_file_path):
        raise FileNotFoundError(f"Input file not found: {mp4_file_path}")
    
    if not shutil.which('ffmpeg'):
        raise FileNotFoundError("ffmpeg not found in PATH")
    
    # Generate output path
    if mp3_output_path is None:
        base_name = Path(mp4_file_path).stem
        mp3_output_path = f"{base_name}.mp3"
    
    # Build command
    cmd = ['ffmpeg', '-i', mp4_file_path]
    
    # Add time-based options if specified
    if 'start_time' in options:
        cmd.extend(['-ss', options['start_time']])
    
    if 'duration' in options:
        cmd.extend(['-t', options['duration']])
    
    # Audio options
    cmd.extend([
        '-vn',                              # No video
        '-acodec', 'mp3',                   # MP3 codec
        '-ab', options['bitrate'],          # Bitrate
        '-ar', options['sample_rate'],      # Sample rate
        '-ac', options['channels'],         # Channels
        '-y',                               # Overwrite
        mp3_output_path
    ])
    
    try:
        # Run command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if not options['quiet']:
            print("FFmpeg output:", result.stderr)
        
        print(f"Successfully extracted MP3: {mp3_output_path}")
        return mp3_output_path
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg failed: {e.stderr}")

# Example usage with advanced options
if __name__ == "__main__":
    try:
        # Extract with custom settings
        result = extract_mp3_advanced(
            "input_video.mp4",
            "output_audio.mp3",
            bitrate='320k',
            start_time='00:01:00',  # Start at 1 minute
            duration='00:03:00',    # Extract 3 minutes
            quiet=False
        )
        print(f"Created: {result}")
        
    except Exception as e:
        print(f"Error: {e}")
