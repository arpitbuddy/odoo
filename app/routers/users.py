from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from app import models, schemas, crud, utils
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from typing import Annotated
import logging
import traceback
from app.logging_config import get_logger
from sqlalchemy.exc import SQLAlchemyError

# Get logger
logger = get_logger("app.routers.users")

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)):
    """Validate token and get current user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the JWT token
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                logger.warning("Token payload missing username")
                raise credentials_exception
            token_data = schemas.TokenData(username=username)
        except (JWTError, ValidationError) as e:
            logger.warning(f"Token validation error: {str(e)}")
            raise credentials_exception
        
        # Get the user from database
        try:
            user = await crud.get_user_by_username(db, username=token_data.username)
            if user is None:
                logger.warning(f"User not found: {token_data.username}")
                raise credentials_exception
            return user
        except SQLAlchemyError as e:
            logger.error(f"Database error during user authentication: {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during authentication",
            )
    except HTTPException:
        # Pass through HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during user authentication: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

@router.post("/", response_model=schemas.User)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new user account"""
    try:
        # Check if email is already registered
        try:
            db_user = await crud.get_user_by_email(db, user.email)
            if db_user:
                logger.warning(f"Registration attempt with existing email: {user.email}")
                raise HTTPException(status_code=400, detail="Email already registered")
        except SQLAlchemyError as e:
            logger.error(f"Database error checking email: {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Error checking email availability")
        
        # Check if username is already registered
        try:
            db_user = await crud.get_user_by_username(db, user.username)
            if db_user:
                logger.warning(f"Registration attempt with existing username: {user.username}")
                raise HTTPException(status_code=400, detail="Username already registered")
        except SQLAlchemyError as e:
            logger.error(f"Database error checking username: {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Error checking username availability")
        
        # Create the user
        try:
            # Now use the CRUD function which has its own error handling
            new_user = await crud.create_user(db, user)
            logger.info(f"New user created: {user.username}")
            return schemas.User(
                id=new_user.id,
                username=new_user.username,
                email=new_user.email,
                full_name=new_user.full_name,
                is_active=new_user.is_active
            )
        except SQLAlchemyError as e:
            logger.error(f"Database error creating user: {str(e)}")
            logger.debug(traceback.format_exc())
            raise HTTPException(status_code=500, detail="Error creating user account")
    except HTTPException:
        # Pass through HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.UserORM = Depends(get_current_user)):
    """Get current user profile"""
    try:
        return current_user
    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error retrieving user profile")
