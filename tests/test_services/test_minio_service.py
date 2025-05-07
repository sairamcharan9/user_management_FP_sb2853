"""
Test module for MinIO service functionality.

Tests that the MinIO service correctly handles image storage operations
and URL generation for profile pictures.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import io
import os
from datetime import datetime, timedelta

from app.services.minio_service import MinioService
from app.config.settings import get_settings


@pytest.fixture
def mock_minio_client():
    """Create a mock MinIO client for testing."""
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    mock_client.put_object.return_value = MagicMock(object_name="test_object")
    
    # Mock the presigned URL generation
    mock_client.get_presigned_url.return_value = "https://minio.example.com/test-bucket/test-object"
    return mock_client


@pytest.fixture
def minio_service(mock_minio_client):
    """Create a MinioService instance with mocked client."""
    with patch('app.services.minio_service.Minio', return_value=mock_minio_client):
        # Get actual settings
        settings = get_settings()
        
        # Create service with real settings but mock client
        service = MinioService()
        service.client = mock_minio_client
        
        # Ensure buckets
        service.profile_pictures_bucket = settings.MINIO_PROFILE_PICTURES_BUCKET
        service.profile_pictures_archive_bucket = settings.MINIO_PROFILE_PICTURES_ARCHIVE_BUCKET
        
        return service


@pytest.mark.asyncio
async def test_upload_profile_picture(minio_service, mock_minio_client):
    """Test that profile picture upload works correctly."""
    # Test data
    user_id = "test-user-123"
    file_content = b"test file content"
    content_type = "image/jpeg"
    
    # Create test file
    file = AsyncMock()
    file.read.return_value = file_content
    
    # Call the method
    result = await minio_service.upload_profile_picture(user_id, file, content_type)
    
    # Check client was called correctly
    mock_minio_client.put_object.assert_called_once()
    
    # Verify the call arguments
    args, kwargs = mock_minio_client.put_object.call_args
    assert kwargs['bucket_name'] == minio_service.profile_pictures_bucket
    assert isinstance(kwargs['data'], io.BytesIO)
    assert kwargs['content_type'] == content_type
    
    # Verify object name contains user ID
    assert user_id in kwargs['object_name']
    
    # Verify result contains URL
    assert "url" in result
    assert isinstance(result["url"], str)
    assert "object_name" in result


@pytest.mark.asyncio
async def test_archive_profile_picture(minio_service, mock_minio_client):
    """Test that profile picture archiving works correctly."""
    # Test data
    user_id = "test-user-123"
    object_name = f"{user_id}/profile-picture.jpg"
    file_content = b"test file content"
    
    # Mock the get_object method
    mock_response = MagicMock()
    mock_response.read.return_value = file_content
    mock_minio_client.get_object.return_value = mock_response
    
    # Call the method
    await minio_service.archive_profile_picture(user_id, object_name)
    
    # Verify get_object was called with correct parameters
    mock_minio_client.get_object.assert_called_once_with(
        minio_service.profile_pictures_bucket, object_name
    )
    
    # Verify put_object was called to store in archive
    mock_minio_client.put_object.assert_called_once()
    
    # Verify archive object name contains original name
    args, kwargs = mock_minio_client.put_object.call_args
    assert object_name in kwargs['object_name']
    assert minio_service.profile_pictures_archive_bucket == kwargs['bucket_name']


@pytest.mark.asyncio
async def test_generate_presigned_url(minio_service, mock_minio_client):
    """Test that presigned URL generation works correctly."""
    # Test data
    object_name = "test-user-123/profile-picture.jpg"
    
    # Call the method
    url = minio_service.generate_presigned_url(object_name)
    
    # Verify client method was called with correct parameters
    mock_minio_client.get_presigned_url.assert_called_once()
    args, kwargs = mock_minio_client.get_presigned_url.call_args
    
    # Check method and bucket
    assert kwargs['method'] == 'GET'
    assert kwargs['bucket_name'] == minio_service.profile_pictures_bucket
    assert kwargs['object_name'] == object_name
    
    # Validate URL
    assert url == "https://minio.example.com/test-bucket/test-object"


@pytest.mark.asyncio
async def test_create_bucket_if_not_exists_existing(minio_service, mock_minio_client):
    """Test bucket creation when bucket already exists."""
    # Mock bucket_exists to return True
    mock_minio_client.bucket_exists.return_value = True
    
    # Call the method
    await minio_service.create_bucket_if_not_exists("test-bucket")
    
    # Verify bucket_exists was called but not make_bucket
    mock_minio_client.bucket_exists.assert_called_once_with("test-bucket")
    mock_minio_client.make_bucket.assert_not_called()


@pytest.mark.asyncio
async def test_create_bucket_if_not_exists_new(minio_service, mock_minio_client):
    """Test bucket creation when bucket doesn't exist."""
    # Mock bucket_exists to return False
    mock_minio_client.bucket_exists.return_value = False
    
    # Call the method
    await minio_service.create_bucket_if_not_exists("test-bucket")
    
    # Verify both methods were called
    mock_minio_client.bucket_exists.assert_called_once_with("test-bucket")
    mock_minio_client.make_bucket.assert_called_once_with("test-bucket")


@pytest.mark.asyncio
async def test_delete_profile_picture(minio_service, mock_minio_client):
    """Test profile picture deletion."""
    # Test data
    object_name = "test-user-123/profile-picture.jpg"
    
    # Call the method
    await minio_service.delete_profile_picture(object_name)
    
    # Verify remove_object was called with correct parameters
    mock_minio_client.remove_object.assert_called_once_with(
        minio_service.profile_pictures_bucket, object_name
    )


@pytest.mark.asyncio
async def test_get_profile_picture_metadata(minio_service, mock_minio_client):
    """Test profile picture metadata retrieval."""
    # Test data
    object_name = "test-user-123/profile-picture.jpg"
    
    # Mock stat_object response
    mock_stat = MagicMock()
    mock_stat.last_modified = datetime.now()
    mock_stat.size = 12345
    mock_stat.content_type = "image/jpeg"
    mock_minio_client.stat_object.return_value = mock_stat
    
    # Call the method
    metadata = await minio_service.get_profile_picture_metadata(object_name)
    
    # Verify stat_object was called correctly
    mock_minio_client.stat_object.assert_called_once_with(
        minio_service.profile_pictures_bucket, object_name
    )
    
    # Verify metadata
    assert metadata.get("size") == 12345
    assert metadata.get("content_type") == "image/jpeg"
    assert "last_modified" in metadata


@pytest.mark.asyncio
async def test_list_profile_pictures(minio_service, mock_minio_client):
    """Test listing of profile pictures for a user."""
    # Test data
    user_id = "test-user-123"
    
    # Mock list_objects response
    mock_obj1 = MagicMock(object_name=f"{user_id}/profile1.jpg", last_modified=datetime.now(), size=1000)
    mock_obj2 = MagicMock(object_name=f"{user_id}/profile2.jpg", last_modified=datetime.now(), size=2000)
    mock_minio_client.list_objects.return_value = [mock_obj1, mock_obj2]
    
    # Call the method
    pictures = await minio_service.list_profile_pictures(user_id)
    
    # Verify list_objects was called correctly with prefix
    mock_minio_client.list_objects.assert_called_once()
    args, kwargs = mock_minio_client.list_objects.call_args
    assert kwargs['bucket_name'] == minio_service.profile_pictures_bucket
    assert kwargs['prefix'] == f"{user_id}/"
    
    # Verify returned data
    assert len(pictures) == 2
    assert pictures[0]["object_name"] == f"{user_id}/profile1.jpg"
    assert pictures[1]["object_name"] == f"{user_id}/profile2.jpg"
    assert "url" in pictures[0]
    assert "url" in pictures[1]
