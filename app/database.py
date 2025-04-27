from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.exc import SQLAlchemyError
import logging
import traceback
import time
from typing import AsyncGenerator

from app.config import settings
from app.logging_config import get_logger

# Get logger for this module
logger = get_logger("app.database")

DATABASE_URL = settings.DATABASE_URL

# Database connection retry settings
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds

# Create the async engine with asyncpg driver
async_db_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
try:
    logger.info(f"Creating async database engine with URL: {async_db_url.replace(':'.join(async_db_url.split(':')[2:]), '***:***')}")
    engine: AsyncEngine = create_async_engine(
        async_db_url, 
        echo=True, 
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=60,
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True  # Check connection validity before use
    )
    logger.info("Async database engine created successfully")
except Exception as e:
    logger.critical(f"Failed to create async database engine: {str(e)}")
    logger.critical(traceback.format_exc())
    raise

# Create a synchronous engine for metadata creation
try:
    sync_db_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
    logger.info(f"Creating sync database engine with URL: {sync_db_url.replace(':'.join(sync_db_url.split(':')[2:]), '***:***')}")
    sync_engine = create_engine(
        sync_db_url, 
        echo=True,
        pool_size=5,
        pool_recycle=3600,
        pool_pre_ping=True
    )
    logger.info("Sync database engine created successfully")
except Exception as e:
    logger.critical(f"Failed to create sync database engine: {str(e)}")
    logger.critical(traceback.format_exc())
    raise

# Create a configured "Session" class
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Create a Base class for declarative models
Base = declarative_base()

# Dependency to get DB session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session with retry logic"""
    db = AsyncSessionLocal()
    retry_count = 0
    connected = False
    
    while retry_count < MAX_RETRIES and not connected:
        try:
            # Test the connection
            await db.execute("SELECT 1")
            connected = True
        except SQLAlchemyError as e:
            retry_count += 1
            if retry_count >= MAX_RETRIES:
                logger.error(f"Failed to connect to database after {MAX_RETRIES} attempts: {str(e)}")
                logger.error(traceback.format_exc())
                await db.close()
                raise
            
            logger.warning(f"Database connection attempt {retry_count} failed: {str(e)}. Retrying in {RETRY_DELAY} seconds.")
            time.sleep(RETRY_DELAY)
            
            # Create a new session for retry
            await db.close()
            db = AsyncSessionLocal()
    
    try:
        logger.debug("Database connection established")
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error during session: {str(e)}")
        logger.error(traceback.format_exc())
        raise
    finally:
        logger.debug("Closing database connection")
        await db.close()
