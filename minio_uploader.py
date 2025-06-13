#!/usr/bin/env python3
"""
MinIO File Uploader Module

This module provides a class to download files from URLs and upload them to a MinIO bucket.
MinIO credentials are read from environment variables.
"""

import os
import urllib.request
import tempfile
import shutil
import subprocess
import glob
from typing import Optional, Union, Dict, Any, List, Tuple
import logging
from urllib.parse import urlparse
from pathlib import Path

# Import MinIO client
try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    raise ImportError("MinIO SDK not found. Install it using: pip install minio")


class MinioUploader:
    """
    Class for downloading files from URLs, optionally converting video files to HLS format (M3U8),
    and uploading them to MinIO buckets.
    MinIO connection details are retrieved from environment variables.
    
    Required environment variables:
        - MINIO_ENDPOINT: MinIO server endpoint (e.g., 'minio.example.com:9000')
        - MINIO_ACCESS_KEY: MinIO access key
        - MINIO_SECRET_KEY: MinIO secret key
        - MINIO_SECURE: Whether to use HTTPS (True/False) - defaults to True if not set
        
    For video conversion functionality, FFmpeg must be installed on the system.
    """

    def __init__(self, use_env_vars: bool = True, ffmpeg_path: Optional[str] = None, **kwargs):
        """
        Initialize MinioUploader with connection details.
        
        Args:
            use_env_vars: Whether to use environment variables for MinIO config.
                          If False, provide connection details in kwargs.
            ffmpeg_path: Path to FFmpeg executable. If None, will try to find it in PATH.
            kwargs: Optional connection parameters if not using environment variables:
                   - endpoint: MinIO server endpoint
                   - access_key: MinIO access key
                   - secret_key: MinIO secret key
                   - secure: Whether to use HTTPS (default: True)
        """
        self.logger = logging.getLogger(__name__)
        self._init_minio_client(use_env_vars, **kwargs)
        
        # Set FFmpeg path or try to find it in the system PATH
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        if self.ffmpeg_path:
            self.logger.info(f"Using FFmpeg at: {self.ffmpeg_path}")
        else:
            self.logger.warning("FFmpeg not found. Video conversion will not be available.")
            
    def _find_ffmpeg(self) -> Optional[str]:
        """Find FFmpeg executable in system PATH."""
        try:
            if os.name == 'nt':  # Windows
                ffmpeg = shutil.which('ffmpeg.exe')
            else:  # Unix/Linux/Mac
                ffmpeg = shutil.which('ffmpeg')
                
            if ffmpeg:
                # Test if FFmpeg works
                result = subprocess.run(
                    [ffmpeg, "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode == 0:
                    return ffmpeg
                    
            return None
        except Exception as e:
            self.logger.warning(f"Error checking for FFmpeg: {str(e)}")
            return None

    def _init_minio_client(self, use_env_vars: bool, **kwargs) -> None:
        """Initialize MinIO client with configuration."""
        if use_env_vars:
            # Get MinIO configuration from environment variables
            endpoint = os.environ.get('MINIO_ENDPOINT')
            access_key = os.environ.get('MINIO_ACCESS_KEY')
            secret_key = os.environ.get('MINIO_SECRET_KEY')
            secure_str = os.environ.get('MINIO_SECURE', 'True')
            secure = secure_str.lower() in ('true', 'yes', '1')
            
            # Check if required environment variables are set
            if not all([endpoint, access_key, secret_key]):
                raise ValueError(
                    "Required MinIO environment variables are not set. "
                    "Please set MINIO_ENDPOINT, MINIO_ACCESS_KEY, and MINIO_SECRET_KEY."
                )
        else:
            # Get MinIO configuration from kwargs
            endpoint = kwargs.get('endpoint')
            access_key = kwargs.get('access_key')
            secret_key = kwargs.get('secret_key')
            secure = kwargs.get('secure', True)
            
            # Check if required parameters are provided
            if not all([endpoint, access_key, secret_key]):
                raise ValueError(
                    "Required MinIO connection parameters are not provided. "
                    "Please provide endpoint, access_key, and secret_key."
                )
        
        # Initialize MinIO client
        try:
            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )
            self.logger.info(f"MinIO client initialized with endpoint: {endpoint}")
        except Exception as e:
            self.logger.error(f"Failed to initialize MinIO client: {str(e)}")
            raise

    def download_file(self, url: str, local_path: Optional[str] = None, verify_ssl: bool = True) -> str:
        """
        Download a file from a URL to a local path.
        
        Args:
            url: URL of the file to download
            local_path: Path where the file will be saved.
                        If None, a temporary file will be created.
            verify_ssl: Whether to verify SSL certificates (default: True).
                        Set to False to disable SSL verification.
        
        Returns:
            The path where the file was saved
        """
        try:
            # Validate URL
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError(f"Invalid URL: {url}")
            
            # If no local path is provided, create a temporary file
            if local_path is None:
                # Extract filename from URL or use a random name
                filename = os.path.basename(parsed_url.path)
                if not filename:
                    filename = f"downloaded_file_{os.urandom(4).hex()}"
                
                # Create a temporary file
                temp_dir = tempfile.gettempdir()
                local_path = os.path.join(temp_dir, filename)
            
            self.logger.info(f"Downloading file from {url} to {local_path} (SSL verify: {verify_ssl})")
            
            # Create custom SSL context if needed
            if not verify_ssl:
                import ssl
                import urllib.request
                
                # Create a context that doesn't verify SSL certificates
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Download the file with custom SSL context
                with urllib.request.urlopen(url, context=ssl_context) as response:
                    with open(local_path, 'wb') as out_file:
                        out_file.write(response.read())
            else:
                # Use the standard method with SSL verification
                urllib.request.urlretrieve(url, local_path)
                
            self.logger.info(f"File downloaded successfully to {local_path}")
            
            return local_path
        except Exception as e:
            self.logger.error(f"Failed to download file from {url}: {str(e)}")
            raise

    def upload_to_minio(self, 
                        file_path: str, 
                        bucket_name: str, 
                        object_name: Optional[str] = None,
                        content_type: Optional[str] = None,
                        metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload a file to a MinIO bucket.
        
        Args:
            file_path: Path to the local file to upload
            bucket_name: Name of the MinIO bucket
            object_name: Name of the object in the bucket. If None, the basename of file_path is used.
            content_type: Content type of the object. If None, it will be guessed.
            metadata: Optional metadata for the object
        
        Returns:
            Dictionary with upload details: 
            {'bucket': bucket_name, 'object_name': object_name, 'etag': etag, 'version_id': version_id}
        """
        try:
            # Check if the file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Check if the bucket exists, create it if not
            if not self.client.bucket_exists(bucket_name):
                self.logger.info(f"Bucket {bucket_name} does not exist. Creating it.")
                self.client.make_bucket(bucket_name)
            
            # If object_name is not provided, use the basename of file_path
            if object_name is None:
                object_name = os.path.basename(file_path)
            
            # Get file size for logging
            file_size = os.path.getsize(file_path)
            
            self.logger.info(f"Uploading file {file_path} ({file_size} bytes) to MinIO bucket {bucket_name} as {object_name}")
            
            # Upload the file
            result = self.client.fput_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type,
                metadata=metadata
            )
            
            upload_info = {
                'bucket': bucket_name,
                'object_name': object_name,
                'etag': result.etag,
                'version_id': result.version_id
            }
            
            self.logger.info(f"File uploaded successfully: {upload_info}")
            return upload_info
            
        except S3Error as e:
            self.logger.error(f"MinIO S3 error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to upload file to MinIO: {str(e)}")
            raise

    def download_from_minio(self, 
                           bucket_name: str, 
                           object_name: str, 
                           local_path: Optional[str] = None,
                           create_dirs: bool = True) -> str:
        """
        Download a file from MinIO bucket to local storage.
        
        Args:
            bucket_name: Name of the MinIO bucket
            object_name: Name of the object in the bucket to download
            local_path: Local path where the file will be saved.
                        If None, the file will be saved in current directory with the object name.
            create_dirs: Whether to create parent directories if they don't exist
        
        Returns:
            The path where the file was saved
        """
        try:
            # Check if the bucket exists
            if not self.client.bucket_exists(bucket_name):
                raise ValueError(f"Bucket '{bucket_name}' does not exist")
            
            # Check if the object exists
            try:
                self.client.stat_object(bucket_name, object_name)
            except S3Error as e:
                if e.code == 'NoSuchKey':
                    raise FileNotFoundError(f"Object '{object_name}' not found in bucket '{bucket_name}'")
                else:
                    raise
            
            # Determine local path
            if local_path is None:
                # Use the object name as the local filename
                local_path = os.path.basename(object_name)
                # If object_name is a path, create the directory structure
                if '/' in object_name:
                    local_path = object_name
            
            # Create parent directories if needed
            if create_dirs:
                parent_dir = os.path.dirname(local_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                    self.logger.info(f"Created directory: {parent_dir}")
            
            self.logger.info(f"Downloading {bucket_name}/{object_name} to {local_path}")
            
            # Download the file
            self.client.fget_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=local_path
            )
            
            # Verify the file was downloaded
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Downloaded file not found at {local_path}")
            
            file_size = os.path.getsize(local_path)
            self.logger.info(f"File downloaded successfully to {local_path} ({file_size} bytes)")
            
            return local_path
            
        except S3Error as e:
            self.logger.error(f"MinIO S3 error during download: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to download file from MinIO: {str(e)}")
            raise

    def download_hls_from_minio(self, 
                               bucket_name: str, 
                               playlist_object_name: str, 
                               local_dir: Optional[str] = None,
                               create_dirs: bool = True) -> Tuple[str, List[str]]:
        """
        Download an HLS video (m3u8 playlist and all associated segment files) from MinIO.
        
        Args:
            bucket_name: Name of the MinIO bucket
            playlist_object_name: Name of the .m3u8 playlist object in the bucket
            local_dir: Local directory where the HLS files will be saved.
                       If None, a directory based on the playlist name will be created.
            create_dirs: Whether to create directories if they don't exist
        
        Returns:
            Tuple of (playlist_local_path, list_of_segment_local_paths)
        """
        try:
            # Check if the bucket exists
            if not self.client.bucket_exists(bucket_name):
                raise ValueError(f"Bucket '{bucket_name}' does not exist")
            
            # Determine local directory
            if local_dir is None:
                playlist_name = os.path.basename(playlist_object_name)
                base_name = os.path.splitext(playlist_name)[0]
                local_dir = f"hls_{base_name}"
            
            # Create local directory
            if create_dirs and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
                self.logger.info(f"Created directory: {local_dir}")
            
            # Download the playlist file first
            playlist_local_path = os.path.join(local_dir, os.path.basename(playlist_object_name))
            self.download_from_minio(
                bucket_name=bucket_name,
                object_name=playlist_object_name,
                local_path=playlist_local_path,
                create_dirs=False
            )
            
            # Parse the playlist to find segment files
            segment_files = []
            try:
                with open(playlist_local_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Look for .ts files in the playlist
                        if line.endswith('.ts') and not line.startswith('#'):
                            segment_files.append(line)
            except Exception as e:
                self.logger.warning(f"Could not parse playlist file: {e}")
                # Fallback: try to find .ts files in the same directory as the playlist
                object_prefix = os.path.dirname(playlist_object_name)
                if object_prefix:
                    object_prefix += '/'
                else:
                    object_prefix = ''
                
                # List objects with the same prefix
                try:
                    objects = self.client.list_objects(
                        bucket_name=bucket_name,
                        prefix=object_prefix
                    )
                    for obj in objects:
                        if obj.object_name.endswith('.ts'):
                            segment_name = os.path.basename(obj.object_name)
                            segment_files.append(segment_name)
                except Exception as list_error:
                    self.logger.error(f"Could not list objects: {list_error}")
            
            # Download all segment files
            downloaded_segments = []
            object_prefix = os.path.dirname(playlist_object_name)
            if object_prefix:
                object_prefix += '/'
            else:
                object_prefix = ''
            
            for segment_file in segment_files:
                segment_object_name = f"{object_prefix}{segment_file}"
                segment_local_path = os.path.join(local_dir, segment_file)
                
                try:
                    self.download_from_minio(
                        bucket_name=bucket_name,
                        object_name=segment_object_name,
                        local_path=segment_local_path,
                        create_dirs=False
                    )
                    downloaded_segments.append(segment_local_path)
                except Exception as e:
                    self.logger.warning(f"Failed to download segment {segment_file}: {e}")
            
            self.logger.info(f"Downloaded HLS playlist and {len(downloaded_segments)} segments to {local_dir}")
            
            return playlist_local_path, downloaded_segments
            
        except Exception as e:
            self.logger.error(f"Failed to download HLS from MinIO: {str(e)}")
            raise

    def list_objects(self, 
                    bucket_name: str, 
                    prefix: Optional[str] = None,
                    recursive: bool = True) -> List[Dict[str, Any]]:
        """
        List objects in a MinIO bucket.
        
        Args:
            bucket_name: Name of the MinIO bucket
            prefix: Filter objects by prefix (optional)
            recursive: Whether to list objects recursively (default: True)
        
        Returns:
            List of dictionaries containing object information
        """
        try:
            # Check if the bucket exists
            if not self.client.bucket_exists(bucket_name):
                raise ValueError(f"Bucket '{bucket_name}' does not exist")
            
            objects_info = []
            
            # List objects
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=recursive
            )
            
            for obj in objects:
                obj_info = {
                    'object_name': obj.object_name,
                    'size': obj.size,
                    'etag': obj.etag,
                    'last_modified': obj.last_modified,
                    'content_type': getattr(obj, 'content_type', None),
                    'is_dir': obj.is_dir if hasattr(obj, 'is_dir') else False
                }
                objects_info.append(obj_info)
            
            self.logger.info(f"Found {len(objects_info)} objects in bucket '{bucket_name}'" + 
                           (f" with prefix '{prefix}'" if prefix else ""))
            
            return objects_info
            
        except S3Error as e:
            self.logger.error(f"MinIO S3 error during list: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to list objects in MinIO: {str(e)}")
            raise

    def convert_mp4_to_hls(self, 
                        input_file: str, 
                        output_dir: Optional[str] = None,
                        segment_time: int = 6,
                        hls_list_size: int = 0,
                        hls_time: int = 6,
                        hls_flags: str = "delete_segments",
                        video_codec: str = "libx264",
                        audio_codec: str = "aac",
                        video_bitrate: str = "800k",
                        audio_bitrate: str = "128k",
                        additional_ffmpeg_args: Optional[List[str]] = None
                        ) -> Tuple[str, str]:
        """
        Convert an MP4 video file to HLS (HTTP Live Streaming) format with M3U8 playlist.
        
        Args:
            input_file: Path to the MP4 input file
            output_dir: Directory where the HLS files will be stored.
                        If None, a temporary directory will be created.
            segment_time: Duration of each segment in seconds (default: 6)
            hls_list_size: Maximum number of playlist entries (0 means all entries)
            hls_time: Target segment duration in seconds
            hls_flags: HLS flags (e.g., "delete_segments+append_list")
            video_codec: Video codec to use (default: libx264)
            audio_codec: Audio codec to use (default: aac)
            video_bitrate: Video bitrate (default: 800k)
            audio_bitrate: Audio bitrate (default: 128k)
            additional_ffmpeg_args: Additional arguments to pass to FFmpeg
            
        Returns:
            Tuple of (playlist_file_path, output_directory)
        """
        if not self.ffmpeg_path:
            raise RuntimeError("FFmpeg not found. Cannot convert video.")
            
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file does not exist: {input_file}")
            
        # Create output directory if necessary
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="hls_conversion_")
        else:
            os.makedirs(output_dir, exist_ok=True)
            
        # Prepare file paths
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        playlist_file = os.path.join(output_dir, f"{base_name}.m3u8")
        segment_pattern = os.path.join(output_dir, f"{base_name}_%03d.ts")
        
        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            "-i", input_file,
            "-c:v", video_codec,
            "-c:a", audio_codec,
            "-b:v", video_bitrate,
            "-b:a", audio_bitrate,
            "-hls_time", str(hls_time),
            "-hls_list_size", str(hls_list_size),
            "-hls_flags", hls_flags,
            "-segment_time", str(segment_time),
            "-f", "hls"
        ]
        
        # Add any additional arguments
        if additional_ffmpeg_args:
            cmd.extend(additional_ffmpeg_args)
            
        # Add output file (must be last)
        cmd.append(playlist_file)
        
        self.logger.info(f"Converting {input_file} to HLS format...")
        self.logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            # Run FFmpeg
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                self.logger.error(f"FFmpeg error: {process.stderr}")
                raise RuntimeError(f"FFmpeg conversion failed: {process.stderr}")
                
            if not os.path.exists(playlist_file):
                raise FileNotFoundError(f"Output playlist file was not created: {playlist_file}")
                
            self.logger.info(f"HLS conversion successful. Playlist: {playlist_file}")
            self.logger.info(f"Created segments: {len(glob.glob(os.path.join(output_dir, '*.ts')))}")
            
            return playlist_file, output_dir
            
        except Exception as e:
            self.logger.error(f"Video conversion failed: {str(e)}")
            raise

    def upload_hls_to_minio(self, 
                           hls_dir: str, 
                           playlist_file: str, 
                           bucket_name: str,
                           object_prefix: Optional[str] = None,
                           keep_local: bool = False,
                           metadata: Optional[Dict[str, str]] = None
                           ) -> Dict[str, Any]:
        """
        Upload an HLS video (m3u8 and all ts files) to MinIO.
        
        Args:
            hls_dir: Directory containing the HLS files
            playlist_file: Path to the main .m3u8 playlist file
            bucket_name: Name of the MinIO bucket
            object_prefix: Prefix to add to object names in MinIO. If None, will use basename of the hls_dir.
            keep_local: Whether to keep the local HLS files after upload
            metadata: Optional metadata for the objects
            
        Returns:
            Dictionary with upload details
        """
        try:
            # Make sure the bucket exists
            if not self.client.bucket_exists(bucket_name):
                self.logger.info(f"Bucket {bucket_name} does not exist. Creating it.")
                self.client.make_bucket(bucket_name)
                
            # Define object prefix
            if object_prefix is None:
                object_prefix = os.path.basename(os.path.normpath(hls_dir))
                
            # Make sure object_prefix ends with a slash if it's not empty
            if object_prefix and not object_prefix.endswith('/'):
                object_prefix += '/'
                
            # Upload all .ts files
            segment_files = glob.glob(os.path.join(hls_dir, "*.ts"))
            uploaded_files = []
            
            for segment_file in segment_files:
                segment_name = os.path.basename(segment_file)
                object_name = f"{object_prefix}{segment_name}"
                
                self.logger.info(f"Uploading segment: {segment_name} to {bucket_name}/{object_name}")
                
                self.client.fput_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    file_path=segment_file,
                    content_type="video/MP2T",
                    metadata=metadata
                )
                
                uploaded_files.append(object_name)
                
            # Upload the playlist file
            playlist_name = os.path.basename(playlist_file)
            playlist_object_name = f"{object_prefix}{playlist_name}"
            
            self.logger.info(f"Uploading playlist: {playlist_name} to {bucket_name}/{playlist_object_name}")
            
            result = self.client.fput_object(
                bucket_name=bucket_name,
                object_name=playlist_object_name,
                file_path=playlist_file,
                content_type="application/x-mpegURL",
                metadata=metadata
            )
            
            uploaded_files.append(playlist_object_name)
            
            # Clean up if needed
            if not keep_local:
                shutil.rmtree(hls_dir, ignore_errors=True)
                self.logger.info(f"Local HLS directory {hls_dir} deleted")
                
            return {
                'bucket': bucket_name,
                'playlist': playlist_object_name,
                'segments': uploaded_files,
                'total_files': len(uploaded_files),
                'etag': result.etag,
                'version_id': result.version_id,
                'prefix': object_prefix
            }
            
        except Exception as e:
            self.logger.error(f"Failed to upload HLS to MinIO: {str(e)}")
            raise

    def download_and_upload(self, 
                           url: str, 
                           bucket_name: str, 
                           object_name: Optional[str] = None,
                           keep_local: bool = False,
                           content_type: Optional[str] = None,
                           metadata: Optional[Dict[str, str]] = None,
                           verify_ssl: bool = True,
                           convert_video: bool = False,
                           hls_options: Optional[Dict[str, Any]] = None
                           ) -> Dict[str, Any]:
        """
        Download a file from a URL and upload it to a MinIO bucket.
        If convert_video is True and the file is an MP4, it will be converted to HLS format.
        
        Args:
            url: URL of the file to download
            bucket_name: Name of the MinIO bucket
            object_name: Name of the object in the bucket. If None, will be extracted from the URL.
            keep_local: Whether to keep the local file after upload (default: False)
            content_type: Content type of the object. If None, it will be guessed.
            metadata: Optional metadata for the object
            verify_ssl: Whether to verify SSL certificates for download (default: True).
                        Set to False to disable SSL verification.
            convert_video: Whether to convert MP4 videos to HLS format before uploading
            hls_options: Dictionary of options for HLS conversion (passed to convert_mp4_to_hls)
            
        Returns:
            Dictionary with upload details
        """
        try:
            # Download the file
            local_path = self.download_file(url, verify_ssl=verify_ssl)
            
            # If object_name is not provided, extract it from the URL
            if object_name is None:
                object_name = os.path.basename(urlparse(url).path)
                # If URL doesn't have a filename, use the local filename
                if not object_name:
                    object_name = os.path.basename(local_path)
            
            # Check if this is an MP4 video file and conversion is requested
            _, ext = os.path.splitext(local_path)
            is_mp4 = ext.lower() in ['.mp4', '.m4v', '.mov']
            
            if convert_video and is_mp4 and self.ffmpeg_path:
                self.logger.info(f"Converting MP4 video to HLS format before upload")
                
                # Prepare conversion options
                conversion_options = hls_options or {}
                
                # Convert the MP4 to HLS
                playlist_file, hls_dir = self.convert_mp4_to_hls(
                    input_file=local_path, 
                    **conversion_options
                )
                
                # Clean up the original download if not needed
                if not keep_local and os.path.exists(local_path):
                    os.remove(local_path)
                    self.logger.info(f"Original downloaded file {local_path} deleted")
                
                # Upload the HLS files
                object_prefix = os.path.splitext(object_name)[0]
                upload_info = self.upload_hls_to_minio(
                    hls_dir=hls_dir,
                    playlist_file=playlist_file,
                    bucket_name=bucket_name,
                    object_prefix=object_prefix,
                    keep_local=keep_local,
                    metadata=metadata
                )
                
                return upload_info
            else:
                # Regular file upload
                upload_info = self.upload_to_minio(
                    file_path=local_path,
                    bucket_name=bucket_name,
                    object_name=object_name,
                    content_type=content_type,
                    metadata=metadata
                )
                
                # Remove the local file if keep_local is False
                if not keep_local and os.path.exists(local_path):
                    os.remove(local_path)
                    self.logger.info(f"Local file {local_path} deleted")
                
                return upload_info
        
        except Exception as e:
            self.logger.error(f"Failed to download and upload file: {str(e)}")
            raise


# Usage example (with doctest format)
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
    # Example usage:
    logging.basicConfig(level=logging.INFO)
    
    # You need to set these environment variables before running:
    # os.environ['MINIO_ENDPOINT'] = 'play.min.io:9000'
    # os.environ['MINIO_ACCESS_KEY'] = 'minioadmin'
    # os.environ['MINIO_SECRET_KEY'] = 'minioadmin'
    # os.environ['MINIO_SECURE'] = 'True'
    
    # Uncomment to test:
    # try:
    #     uploader = MinioUploader()
    #     
    #     # Example 1: Download MP4, convert to HLS, and upload to MinIO
    #     result = uploader.download_and_upload(
    #         url="https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4",
    #         bucket_name="videos",
    #         verify_ssl=False,
    #         convert_video=True,  # Enable video conversion
    #         hls_options={
    #             "segment_time": 4,
    #             "video_bitrate": "1200k",
    #             "audio_bitrate": "160k"
    #         }
    #     )
    #     print(f"HLS conversion and upload result: {result}")
    #     
    #     # Example 2: Download a single file from MinIO
    #     if result.get('playlist'):
    #         downloaded_file = uploader.download_from_minio(
    #             bucket_name="videos",
    #             object_name=result['playlist'],
    #             local_path="./downloaded_playlist.m3u8"
    #         )
    #         print(f"Downloaded playlist to: {downloaded_file}")
    #     
    #     # Example 3: Download entire HLS video (playlist + segments)
    #     if result.get('playlist'):
    #         playlist_path, segments = uploader.download_hls_from_minio(
    #             bucket_name="videos",
    #             playlist_object_name=result['playlist'],
    #             local_dir="./downloaded_hls"
    #         )
    #         print(f"Downloaded HLS to: {playlist_path}")
    #         print(f"Number of segments: {len(segments)}")
    #     
    #     # Example 4: List objects in bucket
    #     objects = uploader.list_objects(bucket_name="videos")
    #     print(f"Objects in bucket: {len(objects)}")
    #     for obj in objects[:5]:  # Show first 5 objects
    #         print(f"  - {obj['object_name']} ({obj['size']} bytes)")
    #         
    #     # To get the streaming URL for the converted video:
    #     if result.get('playlist'):
    #         streaming_url = f"https://{os.environ.get('MINIO_ENDPOINT')}/{result['bucket']}/{result['playlist']}"
    #         print(f"Streaming URL: {streaming_url}")
    #         
    # except Exception as e:
    #     print(f"Error: {e}")
