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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
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
        
        logger.debug(f"Starting upload for user {user_id}, file: {file.filename}, size: {file.size}, content_type: {file.content_type}")
        logger.debug(f"Current user info: {current_user}")
        
        # Validate file size and type before uploading
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image"
            )
        
        try:
            profile_picture_url = await MinioService.upload_profile_picture(file, str(user_id))
            logger.debug(f"Successfully got profile_picture_url: {profile_picture_url}")
        except Exception as upload_error:
            logger.error(f"Error in MinioService.upload_profile_picture: {str(upload_error)}")
            if isinstance(upload_error, HTTPException):
                raise upload_error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file: {str(upload_error)}"
            )
        
        # Update the user's profile picture URL in the database
        update_data = {"profile_picture_url": profile_picture_url}
        logger.debug(f"Attempting to update user with data: {update_data}")
        
        try:
            updated_user = await UserService.update(db, user_id, update_data)
            logger.debug(f"User update result: {updated_user is not None}")
        except Exception as db_error:
            logger.error(f"Error in UserService.update: {str(db_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update user in database: {str(db_error)}"
            )
        
        if not updated_user:
            logger.warning("UserService.update returned None")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user profile picture"
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
        logger.debug(f"Re-raising HTTPException: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Caught unhandled exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading profile picture: {str(e)}"
        )
