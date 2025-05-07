from builtins import str
import pytest
from httpx import AsyncClient
import io
from fastapi import UploadFile
from unittest.mock import patch, MagicMock, AsyncMock
from app.models.user_model import User, UserRole
from app.utils.nickname_gen import generate_nickname
from app.services.minio_service import MinioService


@pytest.mark.asyncio
async def test_upload_profile_picture_access_denied(async_client, verified_user):
    # Create a small test image
    file_content = b"test image content"
    
    # Create a token for a different user to test access control
    from app.services.jwt_service import create_access_token
    from datetime import timedelta
    import uuid
    
    # Create a token for a different user
    # The JWT will have 'sub' field, but get_current_user will convert it to 'user_id' for the route handler
    different_user_id = str(uuid.uuid4())  # Different from verified_user.id
    token_data = {"sub": different_user_id, "role": "AUTHENTICATED"}
    different_user_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=30))
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Test that regular users can't upload profile pictures for others
    headers = {"Authorization": f"Bearer {different_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # Since we're accessing a different user's profile, this should be forbidden
    assert response.status_code == 403


@pytest.fixture
def mock_minio_service(monkeypatch):
    # Create an async mock for the upload_profile_picture method
    async def mock_upload(*args, **kwargs):
        return "http://minio:9001/user-profiles/test-image.jpg"
    
    # Apply the monkeypatch to the class method
    monkeypatch.setattr(MinioService, "upload_profile_picture", mock_upload)
    
    yield
    
    # Clean up after the test
    monkeypatch.undo()

@pytest.mark.asyncio
async def test_upload_profile_picture_admin_allowed(async_client, verified_user, admin_token, mock_minio_service):
    # Create a small test image
    file_content = b"test image content"
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Test that admins can upload profile pictures for any user
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # This should be allowed for admins
    assert response.status_code == 200
    assert "profile_picture_url" in response.json()
    assert response.json()["profile_picture_url"] is not None


@pytest.mark.asyncio
async def test_upload_profile_picture_own_user(async_client, verified_user, mock_minio_service):
    # Create a small test image
    file_content = b"test image content"
    
    # Here we create a token specifically for the verified_user so they can modify their own profile
    from app.services.jwt_service import create_access_token
    from datetime import timedelta
    
    # Create a token that matches the structure expected by our application's dependencies
    # The JWT will have 'sub' field, but get_current_user will convert it to 'user_id' for the route handler
    token_data = {"sub": str(verified_user.id), "role": verified_user.role.name}
    verified_user_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=30))
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Test that users can upload their own profile pictures
    headers = {"Authorization": f"Bearer {verified_user_token}"}
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    # This should work when using a patch to bypass actual Minio storage
    # In a real environment, this would fail without a valid Minio configuration
    assert response.status_code == 200
    assert "profile_picture_url" in response.json()
    assert response.json()["profile_picture_url"] is not None


@pytest.mark.asyncio
async def test_upload_profile_picture_user_not_found(async_client, admin_token):
    # Create a small test image
    file_content = b"test image content"
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Test with a non-existent user ID
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await async_client.post(
        "/users/00000000-0000-0000-0000-000000000000/profile-picture",
        files=files,
        headers=headers
    )
    
    # Should return 404 Not Found
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_profile_picture_no_auth(async_client, verified_user):
    # Create a small test image
    file_content = b"test image content"
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Test without authentication
    response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files
    )
    
    # Should return 401 Unauthorized
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_with_profile_picture(async_client, verified_user, admin_token, mock_minio_service):
    # First, let's upload a profile picture
    file_content = b"test image content"
    
    # Create form data with the file
    files = {
        "file": ("test_image.jpg", file_content, "image/jpeg")
    }
    
    # Upload the profile picture
    headers = {"Authorization": f"Bearer {admin_token}"}
    upload_response = await async_client.post(
        f"/users/{verified_user.id}/profile-picture",
        files=files,
        headers=headers
    )
    
    assert upload_response.status_code == 200
    
    # Now get the user and check that the profile picture URL is included
    get_response = await async_client.get(
        f"/users/{verified_user.id}",
        headers=headers
    )
    
    assert get_response.status_code == 200
    assert "profile_picture_url" in get_response.json()
    assert get_response.json()["profile_picture_url"] is not None
