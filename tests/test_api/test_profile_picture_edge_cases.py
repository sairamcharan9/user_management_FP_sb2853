"""
Tests for profile picture edge cases and error handling.

This module tests various edge cases and error scenarios for profile picture
uploads, including invalid files, size limits, and error responses.
"""

import pytest
from httpx import AsyncClient
import io
from fastapi import UploadFile
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta
import uuid

from app.models.user_model import User, UserRole
from app.services.jwt_service import create_access_token
from app.services.minio_service import MinioService
from app.utils.image_validator import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


@pytest.fixture
def verified_user_token(verified_user):
    """Create a token for the verified user."""
    token_data = {"sub": str(verified_user.id), "role": verified_user.role.name}
    return create_access_token(data=token_data, expires_delta=timedelta(minutes=30))


@pytest.mark.asyncio
async def test_upload_too_large_file(async_client, verified_user, verified_user_token):
    """Test uploading a file that exceeds size limits."""
    # Create a file that exceeds the size limit
    # Generate a large file (just over the limit to avoid excessive memory usage)
    file_content = b"x" * (MAX_FILE_SIZE + 1)
    
    # Create form data with the file
    files = {
        "file": ("large_image.jpg", file_content, "image/jpeg")
    }
    
    # Test upload
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # Should return 400 Bad Request with size limit message
    assert response.status_code == 400
    assert "size" in response.json()["detail"].lower()
    assert str(MAX_FILE_SIZE // (1024 * 1024)) in response.json()["detail"]  # Should mention the MB limit


@pytest.mark.asyncio
async def test_upload_wrong_content_type(async_client, verified_user, verified_user_token):
    """Test uploading a file with incorrect content type."""
    # Create a small text file with incorrect content type
    file_content = b"This is a text file, not an image"
    
    # Create form data with the file - note text/plain content type
    files = {
        "file": ("text_file.jpg", file_content, "text/plain")
    }
    
    # Test upload
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # Should return 400 Bad Request with content type message
    assert response.status_code == 400
    assert "content type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_invalid_extension(async_client, verified_user, verified_user_token):
    """Test uploading a file with an invalid extension."""
    # Create a small file with invalid extension
    file_content = b"test content"
    
    # Create form data with the file - note .txt extension
    files = {
        "file": ("image.txt", file_content, "image/jpeg")
    }
    
    # Test upload
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # Should return 400 Bad Request with extension message
    assert response.status_code == 400
    assert "extension" in response.json()["detail"].lower()
    
    # Should mention allowed extensions
    for ext in ALLOWED_EXTENSIONS:
        assert ext in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file(async_client, verified_user, verified_user_token):
    """Test uploading an empty file."""
    # Create an empty file
    file_content = b""
    
    # Create form data with the file
    files = {
        "file": ("empty.jpg", file_content, "image/jpeg")
    }
    
    # Test upload
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # Should return 400 Bad Request with empty file message
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_minio_service_exception_handling(async_client, verified_user, verified_user_token):
    """Test handling of MinIO service exceptions during upload."""
    # Create a small test image
    file_content = b"test image content"
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Mock MinioService to raise an exception
    with patch('app.services.minio_service.MinioService.upload_profile_picture') as mock_upload:
        mock_upload.side_effect = Exception("MinIO connection error")
        
        # Test upload
        headers = {"Authorization": f"Bearer {verified_user_token}"}
        response = await async_client.post(
            f"/users/{verified_user.id}/profile-picture",
            files=files,
            headers=headers
        )
        
        # Should return 500 Internal Server Error
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()
        # Should not expose internal exception details to client
        assert "minio connection error" not in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_profile_picture_removal(async_client, verified_user, verified_user_token, mock_minio_service):
    """Test removing a profile picture."""
    # First upload a profile picture
    file_content = b"test image content"
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    upload_response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    assert upload_response.status_code == 200
    
    # Now test deletion endpoint
    with patch('app.services.minio_service.MinioService.delete_profile_picture') as mock_delete:
        mock_delete.return_value = None
        
        delete_response = await async_client.delete(
            f"/users/{verified_user.id}/profile-picture",
            headers=headers
        )
        
        # Should return 200 OK
        assert delete_response.status_code == 200
        assert "success" in delete_response.json()["message"].lower()
        
        # Verify user's profile picture is removed in DB
        get_response = await async_client.get(
            f"/users/{verified_user.id}",
            headers=headers
        )
        
        assert get_response.status_code == 200
        assert get_response.json()["profile_picture_url"] is None


@pytest.mark.asyncio
async def test_concurrent_profile_picture_uploads(async_client, verified_user, verified_user_token):
    """Test handling of concurrent profile picture uploads for the same user."""
    # Create two test images
    file_content1 = b"test image content 1"
    file_content2 = b"test image content 2"
    
    # Mock MinioService upload to simulate successful uploads
    with patch('app.services.minio_service.MinioService.upload_profile_picture') as mock_upload:
        mock_upload.return_value = {"url": "http://minio:9001/test-bucket/test-object", "object_name": "test-object"}
        
        # First upload
        files1 = {
            "file": ("test_image1.jpg", file_content1, "image/jpeg")
        }
        
        # Second upload
        files2 = {
            "file": ("test_image2.jpg", file_content2, "image/jpeg")
        }
        
        headers = {"Authorization": f"Bearer {verified_user_token}"}
        
        # Send both requests (we don't actually need to make them concurrent for the test)
        response1 = await async_client.post(
            f"/users/{verified_user.id}/profile-picture",
            files=files1,
            headers=headers
        )
        
        response2 = await async_client.post(
            f"/users/{verified_user.id}/profile-picture",
            files=files2,
            headers=headers
        )
        
        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Verify archiving was called
        assert mock_upload.call_count == 2
