from fastapi import FastAPI, Depends
from app.routers import auth, tickets, users
from app.config import settings
from app.database import engine, Base
from app.database import get_db
from app.crud import get_user_by_username
from app.models import UserORM
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from contextlib import asynccontextmanager
from app.sync import periodic_sync
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("app.main")

# Background task setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task for periodic sync
    sync_task = asyncio.create_task(periodic_sync())
    logger.info("Started background sync task")
    
    yield
    
    # Stop background task
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        logger.info("Background sync task cancelled")

app = FastAPI(
    title="Healthcare Diagnostic Test Booking Support System",
    version="0.1.0",
    lifespan=lifespan
)

# Include routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets"])

@app.on_event("startup")
async def startup():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Healthcare Diagnostic Test Booking Support System"}

@app.get("/api/test")
def test_endpoint():
    """Simple test endpoint to verify API is working"""
    return {"status": "ok", "message": "API is operational"}
