"""
Tests for email verification edge cases and error messages.

This module contains tests specifically for validating email verification
error messages and handling of edge cases.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock
import uuid
from datetime import datetime, timedelta

from app.models.user_model import User, UserRole, VerificationTokenType
from app.models.verification_token_model import VerificationToken
from app.services.jwt_service import create_access_token


@pytest.mark.asyncio
async def test_email_verification_expired_token(async_client, db_session):
    """Test verification with an expired token returns appropriate error."""
    # Create user
    user = User(
        email="expired_token@example.com",
        hashed_password="hashed_password",
        role=UserRole.ANONYMOUS,
        is_verified=False
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create expired verification token
    expired_time = datetime.utcnow() - timedelta(hours=48)  # 48 hours ago
    token = VerificationToken(
        token=str(uuid.uuid4()),
        user_id=user.id,
        expires_at=expired_time,
        token_type=VerificationTokenType.EMAIL_VERIFICATION
    )
    db_session.add(token)
    await db_session.commit()
    
    # Try to verify with expired token
    response = await async_client.get(f"/auth/verify-email?token={token.token}")
    
    # Verify response contains clear expired token message
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_email_verification_invalid_token(async_client):
    """Test verification with an invalid token returns clear error."""
    # Use a random UUID as an invalid token
    invalid_token = str(uuid.uuid4())
    
    # Try to verify with invalid token
    response = await async_client.get(f"/auth/verify-email?token={invalid_token}")
    
    # Verify response contains clear invalid token message
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_email_verification_already_verified(async_client, db_session):
    """Test verification when user is already verified."""
    # Create verified user
    user = User(
        email="already_verified@example.com",
        hashed_password="hashed_password",
        role=UserRole.AUTHENTICATED,
        is_verified=True
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create valid verification token (even though user is already verified)
    expiry = datetime.utcnow() + timedelta(hours=24)
    token = VerificationToken(
        token=str(uuid.uuid4()),
        user_id=user.id,
        expires_at=expiry,
        token_type=VerificationTokenType.EMAIL_VERIFICATION
    )
    db_session.add(token)
    await db_session.commit()
    
    # Try to verify with token
    response = await async_client.get(f"/auth/verify-email?token={token.token}")
    
    # Should still be success, but message should indicate already verified
    assert response.status_code == 200
    assert "already verified" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_resend_verification_rate_limit(async_client, db_session):
    """Test rate limiting for resending verification emails."""
    # Create user
    user = User(
        email="rate_limited@example.com",
        hashed_password="hashed_password",
        role=UserRole.ANONYMOUS,
        is_verified=False
    )
    db_session.add(user)
    await db_session.commit()
    
    # Create user token
    token_data = {"sub": str(user.id), "role": user.role.name}
    user_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=30))
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # First request should succeed
    first_response = await async_client.post("/auth/resend-verification", headers=headers)
    assert first_response.status_code == 200
    
    # Immediate subsequent request should be rate limited
    second_response = await async_client.post("/auth/resend-verification", headers=headers)
    assert second_response.status_code == 429
    assert "try again" in second_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_email_verification_user_role_upgrade(async_client, db_session):
    """Test that user role is upgraded upon successful verification."""
    # Create user with ANONYMOUS role
    user = User(
        email="role_upgrade@example.com",
        hashed_password="hashed_password",
        role=UserRole.ANONYMOUS,
        is_verified=False
    )
    db_session.add(user)
    await db_session.flush()
    
    # Create valid verification token
    expiry = datetime.utcnow() + timedelta(hours=24)
    token = VerificationToken(
        token=str(uuid.uuid4()),
        user_id=user.id,
        expires_at=expiry,
        token_type=VerificationTokenType.EMAIL_VERIFICATION
    )
    db_session.add(token)
    await db_session.commit()
    
    # Verify email
    response = await async_client.get(f"/auth/verify-email?token={token.token}")
    assert response.status_code == 200
    
    # Refresh user from database
    await db_session.refresh(user)
    
    # Verify user is now verified and role is upgraded
    assert user.is_verified == True
    assert user.role == UserRole.AUTHENTICATED
