from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings
import logging
import traceback
from app.logging_config import get_logger

# Get logger for this module
logger = get_logger("app.utils")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        logger.debug(traceback.format_exc())
        return False

def get_password_hash(password: str) -> str:
    """Generate a password hash"""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        logger.debug(traceback.format_exc())
        raise ValueError(f"Could not hash password: {str(e)}")

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token"""
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        logger.debug(traceback.format_exc())
        raise ValueError(f"Could not create access token: {str(e)}")

def decode_access_token(token: str) -> dict:
    """Decode a JWT access token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Invalid JWT token: {str(e)}")
        logger.debug(traceback.format_exc())
        raise ValueError(f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"Error decoding access token: {str(e)}")
        logger.debug(traceback.format_exc())
        raise ValueError(f"Could not decode token: {str(e)}")
