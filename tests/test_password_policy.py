"""
Tests for password policy enforcement functionality.
"""
import pytest
from pydantic import ValidationError
from app.schemas.user_schemas import UserCreate, UserUpdate, validate_password_strength

# Test the password validator function directly
def test_password_validator():
    """Test all aspects of the password strength validation function."""
    # Valid password should pass
    assert validate_password_strength("SecureP@ss123") == "SecureP@ss123"
    
    # Test cases that should fail
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_strength("Short1!")
    
    with pytest.raises(ValueError, match="uppercase letter"):
        validate_password_strength("securepass123!")
    
    with pytest.raises(ValueError, match="lowercase letter"):
        validate_password_strength("SECUREPASS123!")
    
    with pytest.raises(ValueError, match="digit"):
        validate_password_strength("SecurePass!")
    
    with pytest.raises(ValueError, match="special character"):
        validate_password_strength("SecurePass123")

# Test UserCreate with various password inputs
def test_user_create_schema_password_validation():
    """Test password validation in the UserCreate schema."""
    # Valid user data
    valid_user = {
        "email": "test@example.com",
        "password": "SecureP@ss123",
        "role": "AUTHENTICATED"
    }
    
    # This should validate without errors
    user = UserCreate(**valid_user)
    assert user.password == "SecureP@ss123"
    
    # Test invalid password cases
    for invalid_password, expected_error in [
        ("short1!", "at least 8 characters"),
        ("securepass123!", "uppercase letter"),
        ("SECUREPASS123!", "lowercase letter"),
        ("SecurePass!", "digit"),
        ("SecurePass123", "special character")
    ]:
        invalid_user = valid_user.copy()
        invalid_user["password"] = invalid_password
        
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(**invalid_user)
        
        # Check that the error message contains the expected text
        assert expected_error in str(exc_info.value)

# Test UserUpdate with optional password validation
def test_user_update_schema_password_validation():
    """Test password validation in the UserUpdate schema."""
    # Valid update without password
    valid_update = {
        "email": "updated@example.com",
        "role": "AUTHENTICATED"
    }
    
    # This should validate without errors
    update = UserUpdate(**valid_update)
    assert update.password is None
    
    # Valid update with good password
    valid_update_with_password = valid_update.copy()
    valid_update_with_password["password"] = "NewP@ssword123"
    
    update = UserUpdate(**valid_update_with_password)
    assert update.password == "NewP@ssword123"
    
    # Invalid update with bad password
    invalid_update = valid_update.copy()
    invalid_update["password"] = "weak"
    
    with pytest.raises(ValidationError):
        UserUpdate(**invalid_update)
