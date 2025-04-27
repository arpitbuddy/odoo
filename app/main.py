from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
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
import traceback
from app.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()

# Get logger for this module
logger = get_logger("app.main")

# Background task setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task for periodic sync
    try:
        sync_task = asyncio.create_task(periodic_sync())
        logger.info("Started background sync task")
        
        yield
        
        # Stop background task
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            logger.info("Background sync task cancelled")
    except Exception as e:
        logger.error(f"Error in lifespan: {str(e)}")
        logger.error(traceback.format_exc())
        raise

app = FastAPI(
    title="Healthcare Diagnostic Test Booking Support System",
    version="0.1.0",
    lifespan=lifespan
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the error with traceback
    error_msg = f"Unhandled exception: {str(exc)}"
    logger.error(error_msg)
    logger.error(traceback.format_exc())
    
    # Return a clean response to the client
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )

# Include routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets"])

@app.on_event("startup")
async def startup():
    try:
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        logger.error(traceback.format_exc())
        # Don't re-raise to allow app to start even if DB init fails
        # Admin can fix the DB issue while app is running

@app.get("/")
def read_root():
    return {"message": "Welcome to the Healthcare Diagnostic Test Booking Support System"}

@app.get("/api/test")
def test_endpoint():
    """Simple test endpoint to verify API is working"""
    return {"status": "ok", "message": "API is operational"}
