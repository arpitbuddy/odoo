from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError
from app import models, schemas, utils, crud
from app.config import settings
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
import logging
import traceback
from app.logging_config import get_logger

# Get logger
logger = get_logger("app.routers.auth")

router = APIRouter()

@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Login endpoint to get an access token"""
    try:
        # Try to get user
        try:
            user = await crud.get_user_by_username(db, form_data.username)
        except Exception as e:
            logger.error(f"Database error looking up user '{form_data.username}': {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during authentication",
            )
        
        # Verify credentials
        if not user or not utils.verify_password(form_data.password, user.hashed_password):
            logger.warning(f"Failed login attempt for user: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Create and return token
        try:
            access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = utils.create_access_token(
                data={"sub": user.username}, 
                expires_delta=access_token_expires
            )
            logger.info(f"User '{user.username}' logged in successfully")
            return {"access_token": access_token, "token_type": "bearer"}
        except Exception as e:
            logger.error(f"Error creating access token: {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error generating authentication token",
            )
    except HTTPException:
        # Pass through HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
