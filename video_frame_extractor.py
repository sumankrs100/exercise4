import cv2
import numpy as np

class CreatImage:
    """
    A class for extracting frames from video files at specific timestamps
    and returning them as binary data.
    """
    
    def __init__(self):
        """Initialize the CreatImage instance."""
        pass
        
    def extract_frame_at_time(self, video_path, time_seconds=20):
        """
        Extract a frame from a video file at the specified time and return the binary data.
        
        Args:
            video_path (str): Path to the MP4 file
            time_seconds (int): Time in seconds at which to capture the frame (default: 20)
            
        Returns:
            bytes: Binary data of the captured frame in PNG format
            
        Raises:
            ValueError: If the video file cannot be opened or if the specified time
                       is beyond the video duration
        """
        # Open the video file
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Error: Could not open video file {video_path}")
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # Check if the requested time is valid
        if time_seconds > duration:
            cap.release()
            raise ValueError(f"Error: Requested time {time_seconds}s exceeds video duration {duration:.2f}s")
        
        # Set the position to the requested time
        frame_position = int(fps * time_seconds)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
        
        # Read the frame
        ret, frame = cap.read()
        
        # Release the video capture object
        cap.release()
        
        if not ret:
            raise ValueError("Error: Failed to capture frame")
        
        # Convert the frame to binary data in PNG format
        success, buffer = cv2.imencode('.png', frame)
        if not success:
            raise ValueError("Error: Failed to encode frame to PNG")
        
        # Convert to bytes and return
        return buffer.tobytes()
    
    def save_frame_to_file(self, video_path, output_path, time_seconds=20):
        """
        Extract a frame and save it to a file.
        
        Args:
            video_path (str): Path to the MP4 file
            output_path (str): Path where the output image will be saved
            time_seconds (int): Time in seconds at which to capture the frame (default: 20)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get binary data
            binary_data = self.extract_frame_at_time(video_path, time_seconds)
            
            # Write to file
            with open(output_path, 'wb') as f:
                f.write(binary_data)
            
            return True
        except Exception as e:
            print(f"Error saving frame: {e}")
            return False


# Example usage
if __name__ == "__main__":
    extractor = CreatImage()
    
    try:
        # Extract frame at 20 seconds and get binary data
        binary_data = extractor.extract_frame_at_time("path/to/your/video.mp4")
        print(f"Successfully extracted frame. Binary data size: {len(binary_data)} bytes")
        
        # Save to file example
        success = extractor.save_frame_to_file("path/to/your/video.mp4", "output_frame.png")
        if success:
            print("Frame successfully saved to output_frame.png")
    except Exception as e:
        print(f"Error: {e}")
