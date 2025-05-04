# app/security.py
from builtins import Exception, ValueError, bool, int, str
import secrets
import bcrypt
from logging import getLogger
from datetime import datetime, timedelta, timezone

# Set up logging
logger = getLogger(__name__)

def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hashes a password using bcrypt with a specified cost factor.
    
    Args:
        password (str): The plain text password to hash.
        rounds (int): The cost factor that determines the computational cost of hashing.

    Returns:
        str: The hashed password.

    Raises:
        ValueError: If hashing the password fails.
    """
    try:
        salt = bcrypt.gensalt(rounds=rounds)
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed_password.decode('utf-8')
    except Exception as e:
        logger.error("Failed to hash password: %s", e)
        raise ValueError("Failed to hash password") from e

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain text password against a hashed password.
    
    Args:
        plain_password (str): The plain text password to verify.
        hashed_password (str): The bcrypt hashed password.

    Returns:
        bool: True if the password is correct, False otherwise.

    Raises:
        ValueError: If the hashed password format is incorrect or the function fails to verify.
    """
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        logger.error("Error verifying password: %s", e)
        raise ValueError("Authentication process encountered an unexpected error") from e

import json
import base64

def generate_verification_token(expiration_hours: int = 24):
    """
    Generates a secure URL-safe token for email verification with embedded expiration time.
    
    The token includes both a random string and an expiration timestamp, encoded as JSON
    and then base64-encoded to create a single string token.
    
    Args:
        expiration_hours (int): Number of hours before the token expires. Default is 24 hours.
        
    Returns:
        str: A secure token containing embedded expiration information
    """
    # Generate random part of the token
    random_token = secrets.token_urlsafe(16)
    
    # Calculate expiration time
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expiration_hours)
    
    # Create a dictionary with token data
    token_data = {
        "token": random_token,
        "expires": expires_at.isoformat()
    }
    
    # Convert to JSON and encode as base64
    json_data = json.dumps(token_data)
    encoded_token = base64.urlsafe_b64encode(json_data.encode()).decode()
    
    return encoded_token

def verify_token_expiration(token: str) -> tuple[bool, str]:
    """
    Verifies if a token is valid and not expired.
    
    Args:
        token (str): The token to verify
        
    Returns:
        tuple: (is_valid, extracted_token) where is_valid is a boolean indicating if the token
               is valid and not expired, and extracted_token is the original random token string
    """
    try:
        # Decode from base64
        decoded_bytes = base64.urlsafe_b64decode(token.encode())
        decoded_data = json.loads(decoded_bytes.decode())
        
        # Extract token and expiration
        random_token = decoded_data.get("token")
        expiry_str = decoded_data.get("expires")
        
        if not random_token or not expiry_str:
            return False, ""
        
        # Parse the ISO format datetime
        expiry_time = datetime.fromisoformat(expiry_str)
        
        # Check if token is expired
        if datetime.now(timezone.utc) > expiry_time:
            return False, random_token
        
        return True, random_token
    except (ValueError, KeyError, json.JSONDecodeError, base64.binascii.Error):
        return False, ""