"""
Profile Picture API routes for handling upload and management of user profile pictures.

This module provides API endpoints for uploading, viewing, and managing user profile pictures
using Minio as the object storage solution.
"""

from uuid import UUID
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordBearer
from app.dependencies import get_db, require_role
from app.services.minio_service import MinioService
from app.services.user_service import UserService
from app.schemas.user_schemas import UserResponse
from app.utils.link_generation import create_user_links

# Initialize logger
logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@router.post(
    "/users/{user_id}/profile-picture", 
    response_model=UserResponse, 
    status_code=status.HTTP_200_OK,
    tags=["Profile Picture Management"]
)
async def upload_profile_picture(
    user_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
    # Allow users to update their own profile pictures, and admins/managers to update anyone's
    current_user: dict = Depends(require_role(["AUTHENTICATED", "ADMIN", "MANAGER"]))
):
    """
    Upload a profile picture for a user.
    
    Args:
        user_id: UUID of the user whose profile picture is being uploaded
        file: The image file to upload
        
    Returns:
        UserResponse: Updated user information with the profile picture URL
        
    Raises:
        HTTPException: If the user is not found or if there's an error during upload
    """
    # Check if the user exists
    user = await UserService.get_by_id(db, user_id)
    if not user:
        logger.error(f"User {user_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please verify the user exists and try again."
        )
    
    # Check if the current user is authorized to update this profile picture

    # The current_user["user_id"] can contain either the user's EMAIL or UUID from the JWT token (sub claim)
    # We need to check both possibilities to ensure compatibility with all our test cases and clients
    
    logger.debug(f"JWT token user_id value: {current_user['user_id']}")
    logger.debug(f"Database user.id: {user.id}")
    logger.debug(f"Database user.email: {user.email}")
    
    # Check if the user is authorized to update this profile picture
    # Allow the operation if:
    # 1. The user has ADMIN or MANAGER role, OR
    # 2. The user_id in the token matches either the user's email OR their UUID
    if (current_user["role"] not in ["ADMIN", "MANAGER"] and 
            current_user["user_id"] != user.email and 
            current_user["user_id"] != str(user.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile picture"
        )
    
    # Upload the profile picture to Minio
    try:
        # Make sure the file is reset to the beginning
        await file.seek(0)
        
        logger.info(f"Starting upload for user {user_id}, file: {file.filename}, size: {file.size}, content_type: {file.content_type}")
        logger.debug(f"Current user info: {current_user}")
        
        # Validate file content type
        if not file.content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing content type. Please ensure you're uploading a valid image file."
            )
            
        # Validate the file is actually an image
        if not file.content_type.startswith('image/'):
            logger.warning(f"Rejected file upload with invalid content type: {file.content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type: {file.content_type}. Only image files are allowed (jpg, jpeg, png, gif)."
            )
            
        # Validate file has a filename
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing filename. Please ensure your image file has a name."
            )
            
        # Validate file extension
        valid_extensions = [".jpg", ".jpeg", ".png", ".gif"]
        file_ext = ".".join(file.filename.lower().split(".")[1:]) if "." in file.filename else ""
        if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
            logger.warning(f"Rejected file with invalid extension: {file_ext}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension: .{file_ext}. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        try:
            profile_picture_url = await MinioService.upload_profile_picture(file, str(user_id))
            logger.info(f"Successfully uploaded profile picture for user {user_id}, URL: {profile_picture_url}")
        except HTTPException as http_error:
            # Re-raise HTTP exceptions from the MinioService with their original status code and message
            logger.warning(f"HTTP error during profile picture upload: {http_error.detail}")
            raise
        except Exception as upload_error:
            # For unexpected errors, provide a more generic message to the client
            # but log the detailed error for debugging
            error_message = str(upload_error)
            logger.error(f"Error in MinioService.upload_profile_picture: {error_message}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store profile picture. Please try again or contact support if the problem persists."
            )
        
        # Update the user's profile picture URL in the database
        update_data = {"profile_picture_url": profile_picture_url}
        logger.info(f"Attempting to update user {user_id} with profile picture URL")
        logger.debug(f"Update data: {update_data}")
        
        try:
            updated_user = await UserService.update(db, user_id, update_data)
            logger.info(f"Profile picture update operation completed successfully for user {user_id}")
            if not updated_user:
                logger.error(f"UserService.update returned None for user {user_id}")
        except Exception as db_error:
            error_message = str(db_error)
            logger.error(f"Error updating user {user_id} in database: {error_message}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user profile with new picture. Please try again later."
            )
        
        if not updated_user:
            logger.error(f"User {user_id} not found after attempted database update")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please verify the user exists and try again."
            )
        
        # Return the updated user information
        try:
            logger.debug(f"Creating response with user ID: {updated_user.id}")
            # First create the model from the database object
            response = UserResponse.model_validate(updated_user)
            
            # Now add HATEOAS links as a property to the response dict
            response_dict = response.model_dump()
            response_dict['links'] = create_user_links(updated_user.id, request)
            
            logger.debug("Response created successfully")
            return response_dict
        except Exception as response_error:
            logger.error(f"Error creating response: {str(response_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create response: {str(response_error)}"
            )
    
    except HTTPException as e:
        # Re-raise HTTP exceptions from the Minio service
        logger.error(f"HTTPException: {e.detail}")
        raise
    except Exception as e:
        error_message = str(e)
        logger.error(f"Unexpected exception during profile picture update for user {user_id}: {error_message}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Our team has been notified."
        )
