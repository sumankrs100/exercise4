import os
import subprocess
import logging
import uuid
from minio import Minio
from minio.error import S3Error

class ConvertM3U8:
    """
    A class to convert MP4 video files to HLS format (M3U8) and upload to MinIO.
    This class uses FFmpeg to perform the conversion.
    """
    
    def __init__(self, ffmpeg_path="ffmpeg", minio_endpoint=None, minio_access_key=None, 
                 minio_secret_key=None, minio_secure=True):
        """
        Initialize the ConvertM3U8 class.
        
        Args:
            ffmpeg_path (str): Path to the FFmpeg executable. Defaults to "ffmpeg",
                              which works if FFmpeg is in your system PATH.
            minio_endpoint (str): MinIO server endpoint (e.g., "minio.example.com:9000")
            minio_access_key (str): MinIO access key
            minio_secret_key (str): MinIO secret key
            minio_secure (bool): Use secure (HTTPS) connection to MinIO
        """
        self.ffmpeg_path = ffmpeg_path
        self.minio_client = None
        
        # Initialize MinIO client if credentials are provided
        if minio_endpoint and minio_access_key and minio_secret_key:
            self.minio_client = Minio(
                endpoint=minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
                secure=minio_secure
            )
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('ConvertM3U8')
    
    def convert_to_m3u8(self, mp4_path, output_dir=None, segment_duration=10, 
                        playlist_name="playlist", quality_levels=None, bucket_name=None,
                        folder_prefix=None, upload_to_minio=False):
        """
        Convert an MP4 file to M3U8 (HLS) format and optionally upload to MinIO.
        
        Args:
            mp4_path (str): Path to the MP4 file to convert.
            output_dir (str, optional): Directory to save the M3U8 file and segments.
                                       If None, uses the same directory as the MP4 file.
            segment_duration (int, optional): Duration of each segment in seconds. Defaults to 10.
            playlist_name (str, optional): Base name for the playlist files. Defaults to "playlist".
            quality_levels (list, optional): List of dictionaries specifying quality levels.
                                           Each dict should have 'resolution' and 'bitrate' keys.
                                           If None, only one quality level is created.
            bucket_name (str, optional): MinIO bucket name. Required if upload_to_minio is True.
            folder_prefix (str, optional): Folder prefix within the bucket. If None, a UUID is generated.
            upload_to_minio (bool, optional): Whether to upload files to MinIO. Defaults to False.
        
        Returns:
            tuple: (path to the master playlist file if successful or None if failed,
                   MinIO folder path if uploaded to MinIO or None otherwise)
        """
        # Validate input file
        if not os.path.isfile(mp4_path):
            self.logger.error(f"Input file not found: {mp4_path}")
            return None, None
        
        # Set output directory
        if output_dir is None:
            output_dir = os.path.dirname(mp4_path)
            if not output_dir:
                output_dir = "."
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Default quality level if none provided
        if quality_levels is None:
            quality_levels = [
                {"resolution": "1280x720", "bitrate": "2000k"}
            ]
            
        # Validate MinIO settings if upload is requested
        if upload_to_minio:
            if not self.minio_client:
                self.logger.error("MinIO client not initialized. Provide credentials during class initialization.")
                return None, None
            if not bucket_name:
                self.logger.error("Bucket name is required for MinIO upload.")
                return None, None
            
            # Generate folder prefix if not provided
            if not folder_prefix:
                folder_prefix = f"hls_{str(uuid.uuid4())}"
        
        try:
            master_playlist_path = os.path.join(output_dir, f"{playlist_name}.m3u8")
            
            # Create master playlist file
            with open(master_playlist_path, 'w') as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                
                for i, quality in enumerate(quality_levels):
                    variant_playlist = f"{playlist_name}_{i}.m3u8"
                    f.write(f'#EXT-X-STREAM-INF:BANDWIDTH={self._bitrate_to_bandwidth(quality["bitrate"])},RESOLUTION={quality["resolution"]}\n')
                    f.write(f"{variant_playlist}\n")
            
            # Create variant playlists and segments
            for i, quality in enumerate(quality_levels):
                variant_playlist = os.path.join(output_dir, f"{playlist_name}_{i}.m3u8")
                segment_pattern = os.path.join(output_dir, f"{playlist_name}_{i}_%03d.ts")
                
                cmd = [
                    self.ffmpeg_path,
                    "-i", mp4_path,
                    "-profile:v", "main",
                    "-vf", f"scale={quality['resolution'].replace('x', ':')}",
                    "-c:v", "libx264",
                    "-b:v", quality["bitrate"],
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-hls_time", str(segment_duration),
                    "-hls_list_size", "0",
                    "-hls_segment_filename", segment_pattern,
                    "-f", "hls",
                    variant_playlist
                ]
                
                self.logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                if result.returncode != 0:
                    self.logger.error(f"FFmpeg error: {result.stderr.decode()}")
                    return None, None
            
            self.logger.info(f"Successfully converted {mp4_path} to HLS format")
            
            # Upload to MinIO if requested
            minio_folder_path = None
            if upload_to_minio:
                minio_folder_path = self._upload_to_minio(output_dir, bucket_name, folder_prefix)
                if not minio_folder_path:
                    self.logger.warning("Conversion successful but MinIO upload failed")
            
            return master_playlist_path, minio_folder_path
            
        except Exception as e:
            self.logger.error(f"Error converting file: {str(e)}")
            return None, None
    
    def _bitrate_to_bandwidth(self, bitrate):
        """
        Convert bitrate string (like '2000k') to bandwidth integer value.
        
        Args:
            bitrate (str): Bitrate string.
            
        Returns:
            int: Bandwidth value in bits per second.
        """
        multiplier = 1000
        value = bitrate.lower().rstrip('k')
        try:
            return int(value) * multiplier
        except ValueError:
            return 2000000  # Default to 2Mbps if conversion fails
            
    def _upload_to_minio(self, local_dir, bucket_name, folder_prefix):
        """
        Upload all files in a directory to MinIO.
        
        Args:
            local_dir (str): Local directory containing files to upload.
            bucket_name (str): MinIO bucket name.
            folder_prefix (str): Folder prefix within the bucket.
            
        Returns:
            str: MinIO folder path if successful, None otherwise.
        """
        try:
            # Check if bucket exists, create if it doesn't
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                self.logger.info(f"Created bucket: {bucket_name}")

            # Get list of files to upload
            files_to_upload = []
            for root, _, files in os.walk(local_dir):
                for file in files:
                    if file.endswith('.m3u8') or file.endswith('.ts'):
                        files_to_upload.append(os.path.join(root, file))
            
            # Upload each file
            for file_path in files_to_upload:
                file_name = os.path.basename(file_path)
                object_name = f"{folder_prefix}/{file_name}"
                
                self.minio_client.fput_object(
                    bucket_name, object_name, file_path,
                    content_type="application/x-mpegURL" if file_path.endswith('.m3u8') else "video/MP2T"
                )
                self.logger.info(f"Uploaded {file_path} to {bucket_name}/{object_name}")
            
            # Return the folder path in MinIO
            return f"{bucket_name}/{folder_prefix}"
            
        except S3Error as e:
            self.logger.error(f"MinIO error: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Error uploading to MinIO: {str(e)}")
            return None


if __name__ == "__main__":
    # Example usage
    converter = ConvertM3U8(
        # MinIO configuration
        minio_endpoint="play.min.io:9000",  # Example MinIO server
        minio_access_key="minioadmin",      # Default access key
        minio_secret_key="minioadmin",      # Default secret key
        minio_secure=True                   # Use HTTPS
    )
    input_file = "example.mp4"
    
    # Simple conversion with default settings (no MinIO upload)
    local_path, _ = converter.convert_to_m3u8(input_file)
    
    # Simple conversion with MinIO upload
    """
    local_path, minio_path = converter.convert_to_m3u8(
        mp4_path=input_file,
        bucket_name="videos",
        upload_to_minio=True
    )
    """
    
    # Advanced conversion with multiple quality levels and MinIO upload
    """
    local_path, minio_path = converter.convert_to_m3u8(
        mp4_path=input_file,
        output_dir="output",
        segment_duration=6,
        playlist_name="video",
        quality_levels=[
            {"resolution": "1920x1080", "bitrate": "5000k"},
            {"resolution": "1280x720", "bitrate": "3000k"},
            {"resolution": "854x480", "bitrate": "1000k"},
            {"resolution": "640x360", "bitrate": "500k"}
        ],
        bucket_name="videos",
        folder_prefix="my_video_hls",
        upload_to_minio=True
    )
    """
    
    if local_path:
        print(f"Conversion successful. Master playlist available at: {local_path}")
        if minio_path:
            print(f"Files uploaded to MinIO path: {minio_path}")
    else:
        print("Conversion failed.")
