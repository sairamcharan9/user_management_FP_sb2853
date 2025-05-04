# test_token_expiration.py
import pytest
from datetime import datetime, timedelta, timezone
import json
import base64
from app.utils.security import generate_verification_token, verify_token_expiration
from app.services.user_service import UserService


def test_generate_verification_token():
    """Test that generating verification token returns a valid base64-encoded string."""
    token = generate_verification_token()
    assert token is not None
    assert isinstance(token, str)
    
    # Verify it's a valid base64 token
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        assert isinstance(decoded, str)
        
        # Verify JSON structure
        token_data = json.loads(decoded)
        assert "token" in token_data
        assert "expires" in token_data
    except Exception as e:
        pytest.fail(f"Token is not properly formatted: {e}")


def test_token_expiration():
    """Test that tokens correctly track expiration time."""
    # Create a token with 1-hour expiration
    token = generate_verification_token(expiration_hours=1)
    
    # Verify token is valid now
    is_valid, random_token = verify_token_expiration(token)
    assert is_valid is True
    assert isinstance(random_token, str)
    
    # Decode and modify expiration to be in the past
    decoded_bytes = base64.urlsafe_b64decode(token.encode())
    token_data = json.loads(decoded_bytes.decode())
    
    # Set expiration to 2 hours ago
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    token_data["expires"] = past_time.isoformat()
    
    # Re-encode with expired timestamp
    expired_json = json.dumps(token_data)
    expired_token = base64.urlsafe_b64encode(expired_json.encode()).decode()
    
    # Verify token is now invalid
    is_valid, _ = verify_token_expiration(expired_token)
    assert is_valid is False


def test_token_invalid_format():
    """Test handling of malformed tokens."""
    # Test completely invalid token
    is_valid, token = verify_token_expiration("not_a_valid_token")
    assert is_valid is False
    assert token == ""
    
    # Test valid base64 but invalid JSON
    invalid_json = base64.urlsafe_b64encode(b"not_json").decode()
    is_valid, token = verify_token_expiration(invalid_json)
    assert is_valid is False
    
    # Test valid JSON but missing fields
    incomplete_data = json.dumps({"only_token": "value"})
    incomplete_token = base64.urlsafe_b64encode(incomplete_data.encode()).decode()
    is_valid, token = verify_token_expiration(incomplete_token)
    assert is_valid is False


def test_token_with_custom_expiration():
    """Test creating tokens with different expiration times."""
    # Token with short expiration
    short_token = generate_verification_token(expiration_hours=1)
    decoded_short = json.loads(base64.urlsafe_b64decode(short_token.encode()).decode())
    short_expiry = datetime.fromisoformat(decoded_short["expires"])
    
    # Token with longer expiration
    long_token = generate_verification_token(expiration_hours=48)
    decoded_long = json.loads(base64.urlsafe_b64decode(long_token.encode()).decode())
    long_expiry = datetime.fromisoformat(decoded_long["expires"])
    
    # The long token should expire later than the short token
    assert long_expiry > short_expiry
    assert (long_expiry - short_expiry) > timedelta(hours=40)  # Roughly 47 hours difference
