from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine

from app.config import settings

DATABASE_URL = settings.DATABASE_URL

# Create the async engine with asyncpg driver
async_db_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine: AsyncEngine = create_async_engine(async_db_url, echo=True, future=True)

# Create a synchronous engine for metadata creation
sync_engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"), echo=True)

# Create a configured "Session" class
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Create a Base class for declarative models
Base = declarative_base()

# Dependency to get DB session
async def get_db():
    """Dependency that provides a database session"""
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()
