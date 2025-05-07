"""
Minio Service for handling file storage operations.

This service provides methods for interacting with Minio, an object storage server.
It handles operations such as uploading, retrieving, and deleting files from Minio.
"""

from builtins import classmethod, str
import os
from typing import Optional, Tuple, List
import uuid
import io
from datetime import timedelta, datetime
from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile, HTTPException, status
import logging
from app.dependencies import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class MinioService:
    """
    Service for interacting with Minio object storage.
    Provides methods for uploading, retrieving, and deleting files.
    """
    
    @classmethod
    def get_client(cls) -> Minio:
        """
        Get a configured Minio client instance.
        
        Returns:
            Minio: A configured Minio client
        """
        return Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
    
    @classmethod
    async def upload_profile_picture(cls, file: UploadFile, user_id: str) -> str:
        """
        Upload a profile picture to Minio.
        
        Preserves history by using timestamped filenames, maintaining all previous
        versions of profile pictures while returning the URL of the latest one.
        
        Args:
            file (UploadFile): The file to upload
            user_id (str): The user ID to associate with the file
            
        Returns:
            str: The URL of the uploaded file
            
        Raises:
            HTTPException: If the file upload fails
        """
        logger.info(f"Starting upload for user {user_id}, file: {file.filename}, content-type: {file.content_type}")
        client = cls.get_client()
        bucket_name = settings.minio_bucket_name
        
        # Ensure bucket exists
        try:
            logger.info(f"Checking if bucket {bucket_name} exists")
            if not client.bucket_exists(bucket_name):
                logger.info(f"Creating bucket: {bucket_name}")
                client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
        except S3Error as e:
            logger.error(f"Error checking/creating bucket: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize storage: {str(e)}"
            )
        
        # Make sure we have a valid filename
        if not file.filename:
            file.filename = f"profile_{uuid.uuid4()}.jpg"
            logger.info(f"Generated filename: {file.filename} for missing filename")
            
        # Generate a timestamped filename to preserve history
        file_extension = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create archive object name with timestamp for history preservation
        archive_name = f"profile_pictures/{user_id}/archive/profile_{timestamp}{file_extension}"
        
        # Use a simple, consistent name for the active profile picture
        # This ensures the database URL never changes and stays short
        active_name = f"profile_pictures/{user_id}/profile{file_extension}"
        
        logger.info(f"Archive name: {archive_name}")
        logger.info(f"Active name: {active_name}")
        
        # Upload the file
        try:
            # Reset file cursor to beginning to ensure we read the full file
            await file.seek(0)
            file_data = await file.read()
            file_size = len(file_data)
            logger.info(f"Read file data, size: {file_size} bytes")
            
            # Debug log for the first few bytes to check if file is actually received
            if file_size > 0:
                preview = "".join([f"{b:02x}" for b in file_data[:20]])
                logger.info(f"File data preview (first 20 bytes): {preview}")
            else:
                logger.warning("File data is empty! This indicates the file was not properly uploaded.")
            
            # Validate file size (limit to 5MB)
            if file_size > 5 * 1024 * 1024:  # 5MB in bytes
                logger.warning(f"File size {file_size} exceeds limit")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File size exceeds the 5MB limit"
                )
                
            # Validate file type (only allow images)
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            if file_extension.lower() not in valid_extensions:
                logger.warning(f"Invalid file extension: {file_extension}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File type not allowed. Allowed types: {', '.join(valid_extensions)}"
                )
            
            # Set a default content type if none provided
            content_type = file.content_type
            if not content_type or not content_type.startswith('image/'):
                content_type = f"image/{file_extension[1:].lower()}" if file_extension != '.jpg' else "image/jpeg"
                logger.info(f"Using default content type: {content_type}")
            
            # Wrap bytes in a file-like object (BytesIO) that has a read() method
            logger.info(f"Putting object to Minio: {archive_name}, size: {file_size}, type: {content_type}")
            
            # Ensure we have actual file data
            if file_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Empty file received. Please select a valid image file."
                )
                
            # Add extra validation for browser uploads
            if not file_data.startswith(b'\xff\xd8') and not file_data.startswith(b'\x89PNG') and not file_data.startswith(b'GIF'):
                logger.warning(f"File data doesn't have valid image headers")
                # Continue anyway - trust the content type validation above
                
            file_data_io = io.BytesIO(file_data)
            # First upload to the archive for history preservation
            try:
                client.put_object(
                    bucket_name,
                    archive_name,
                    file_data_io,
                    file_size,
                    content_type=content_type
                )
                logger.info(f"Successfully uploaded archive copy to {archive_name}")
            except Exception as archive_error:
                logger.error(f"Failed to upload archive copy: {archive_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error saving archive copy: {str(archive_error)}"
                )
            
            # Reset the file data IO position for the second upload
            file_data_io.seek(0)
            
            # Then upload with the consistent name for the active profile picture
            try:
                client.put_object(
                    bucket_name,
                    active_name,
                    file_data_io,
                    file_size,
                    content_type=content_type
                )
                logger.info(f"Successfully uploaded active copy to {active_name}")
            except Exception as active_error:
                logger.error(f"Failed to upload active copy: {active_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error saving active copy: {str(active_error)}"
                )
            
            logger.info(f"Stored profile picture in both archive and active locations")
            
            # Generate a fully qualified URL for database storage
            # Must include http(s):// to pass URL validation in the schema
            base_url = "https://example.com"  # This is a placeholder that will be replaced in production
            url = f"{base_url}/profiles/{user_id}/picture"
            logger.info(f"Upload successful. Full URL for database: {url}")
            
            return url
            
        except S3Error as e:
            logger.error(f"S3Error uploading file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to storage: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file upload: {str(e)}"
            )
    
    @classmethod
    def get_file_url(cls, object_name: str) -> str:
        """
        Get a URL for accessing a file in Minio.
        
        Args:
            object_name (str): The name of the object in Minio
            
        Returns:
            str: The URL for accessing the file
        """
        client = cls.get_client()
        bucket_name = settings.minio_bucket_name
        
        try:
            # Generate complete URLs for database storage that will pass URL validation
            # Extract user_id from object name if possible
            user_id = ""
            parts = object_name.split('/')
            if len(parts) > 1:
                user_id = parts[1]
            
            # Must include http(s):// to pass URL validation in the schema
            base_url = "https://example.com"  # Placeholder for production URL
            short_url = f"{base_url}/profiles/{user_id}/picture"
            
            return short_url
        except Exception as e:
            logger.error(f"Error generating file URL: {e}")
            return ""
    
    @classmethod
    def get_latest_profile_picture(cls, user_id: str) -> str:
        """
        Find the most recent profile picture for a user.
        
        Args:
            user_id (str): The user ID to find the latest profile picture for
            
        Returns:
            str: Object name of the latest profile picture, or empty string if none found
        """
        pictures = cls.find_user_profile_pictures(user_id)
        
        if not pictures:
            return ""
            
        # Sort by timestamp in filename (profile_YYYYMMDD_HHMMSS.ext)
        pictures.sort(reverse=True)  # Most recent first based on object name
        return pictures[0] if pictures else ""
    
    @classmethod
    def find_user_profile_pictures(cls, user_id: str) -> List[str]:
        """
        Find all profile pictures for a user in Minio.
        This can be used to clean up old profile pictures if needed.
        
        Args:
            user_id (str): The user ID to find profile pictures for
            
        Returns:
            list: List of object names for the user's profile pictures
        """
        client = cls.get_client()
        bucket_name = settings.minio_bucket_name
        prefix = f"profile_pictures/{user_id}/"
        
        try:
            objects = client.list_objects(bucket_name, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except Exception as e:
            logger.error(f"Error listing user profile pictures: {e}")
            return []
    
    @classmethod
    def delete_file(cls, object_name: str) -> bool:
        """
        Delete a file from Minio.
        
        Args:
            object_name (str): The name of the object to delete
            
        Returns:
            bool: True if the file was deleted, False otherwise
        """
        client = cls.get_client()
        bucket_name = settings.minio_bucket_name
        
        try:
            client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted file: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Error deleting file: {e}")
            return False
