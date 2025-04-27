from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.models import UserORM, TicketORM, TicketMessageORM
from app.schemas import UserCreate, TicketCreate, Ticket, TicketMessageCreate
from app.utils import get_password_hash
from datetime import datetime
from typing import Optional, Dict, Any, Union, List
from sqlalchemy import func
import logging
import traceback

# Set up logger
logger = logging.getLogger("app.crud")

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[UserORM]:
    """Get a user by email address"""
    try:
        result = await db.execute(select(UserORM).where(UserORM.email == email))
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_user_by_email: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[UserORM]:
    """Get a user by username"""
    try:
        result = await db.execute(select(UserORM).where(UserORM.username == username))
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_user_by_username: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def create_user(db: AsyncSession, user: UserCreate) -> UserORM:
    """Create a new user"""
    try:
        hashed_password = get_password_hash(user.password)
        db_user = UserORM(
            username=user.username, 
            email=user.email, 
            full_name=user.full_name, 
            hashed_password=hashed_password
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        logger.info(f"Created new user: {user.username}")
        return db_user
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error in create_user: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

# Ticket operations
async def get_tickets_by_user_id(db: AsyncSession, user_id: int) -> List[TicketORM]:
    """Get all tickets for a user"""
    try:
        result = await db.execute(
            select(TicketORM)
            .where(TicketORM.user_id == user_id)
            .order_by(TicketORM.created_at.desc())
        )
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_tickets_by_user_id for user {user_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_filtered_tickets(
    db: AsyncSession, 
    user_id: int, 
    status: Optional[str] = None, 
    priority: Optional[str] = None
) -> List[TicketORM]:
    """Get tickets filtered by status and priority"""
    try:
        query = select(TicketORM).where(TicketORM.user_id == user_id)
        
        # Apply filters if provided
        if status:
            query = query.where(TicketORM.status == status)
        
        if priority:
            query = query.where(TicketORM.priority == priority)
        
        # Order by creation date, newest first
        query = query.order_by(TicketORM.created_at.desc())
        
        result = await db.execute(query)
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_filtered_tickets for user {user_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_ticket_by_id(db: AsyncSession, ticket_id: int) -> Optional[TicketORM]:
    """Get a ticket by ID"""
    try:
        result = await db.execute(select(TicketORM).where(TicketORM.id == ticket_id))
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_ticket_by_id for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_ticket_by_odoo_id(db: AsyncSession, odoo_id: int) -> Optional[TicketORM]:
    """Get a ticket by its Odoo ID"""
    try:
        result = await db.execute(select(TicketORM).where(TicketORM.odoo_ticket_id == odoo_id))
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_ticket_by_odoo_id for Odoo ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def create_ticket(db: AsyncSession, ticket: TicketCreate, user_id: int, odoo_id: int = None) -> TicketORM:
    """Create a ticket in the database with optional Odoo ID"""
    try:
        db_ticket = TicketORM(
            title=ticket.name,
            description=ticket.description,
            priority=ticket.priority,
            user_id=user_id,
            odoo_ticket_id=odoo_id,
            status="new",
        )
        
        # Add optional fields if they exist
        if hasattr(ticket, 'diagnostic_test_id') and ticket.diagnostic_test_id is not None:
            db_ticket.diagnostic_test_id = ticket.diagnostic_test_id
        if hasattr(ticket, 'lab_id') and ticket.lab_id is not None:
            db_ticket.lab_id = ticket.lab_id
        if hasattr(ticket, 'booking_id') and ticket.booking_id is not None:
            db_ticket.booking_id = ticket.booking_id
            
        db.add(db_ticket)
        await db.commit()
        await db.refresh(db_ticket)
        logger.info(f"Created ticket ID {db_ticket.id} for user {user_id}" + 
                    (f", linked to Odoo ID {odoo_id}" if odoo_id else ""))
        return db_ticket
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error in create_ticket for user {user_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def update_ticket(db: AsyncSession, ticket_id: int, ticket_data: dict) -> Optional[TicketORM]:
    """Update a ticket with dictionary of values"""
    try:
        db_ticket = await get_ticket_by_id(db, ticket_id)
        if db_ticket is None:
            logger.warning(f"Attempted to update non-existent ticket {ticket_id}")
            return None
            
        for key, value in ticket_data.items():
            setattr(db_ticket, key, value)
            
        db_ticket.updated_at = datetime.utcnow()  # Always update the timestamp
        await db.commit()
        await db.refresh(db_ticket)
        logger.info(f"Updated ticket ID {ticket_id} with fields: {list(ticket_data.keys())}")
        return db_ticket
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error in update_ticket for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def delete_ticket(db: AsyncSession, ticket_id: int) -> Optional[TicketORM]:
    """Delete a ticket by ID"""
    try:
        db_ticket = await get_ticket_by_id(db, ticket_id)
        if db_ticket is None:
            logger.warning(f"Attempted to delete non-existent ticket {ticket_id}")
            return None
        await db.delete(db_ticket)
        await db.commit()
        logger.info(f"Deleted ticket ID {ticket_id}")
        return db_ticket
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error in delete_ticket for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

# Ticket message operations
async def get_ticket_messages(db: AsyncSession, ticket_id: int) -> List[TicketMessageORM]:
    """Get all messages for a ticket"""
    try:
        result = await db.execute(
            select(TicketMessageORM)
            .where(TicketMessageORM.ticket_id == ticket_id)
            .order_by(TicketMessageORM.created_at)
        )
        return result.scalars().all()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_ticket_messages for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def create_ticket_message(
    db: AsyncSession, 
    ticket_id: int, 
    message: str, 
    is_from_support: bool = False, 
    odoo_message_id: int = None
) -> TicketMessageORM:
    """Create a new message for a ticket"""
    try:
        db_message = TicketMessageORM(
            ticket_id=ticket_id,
            message=message,
            is_from_support=is_from_support,
            odoo_message_id=odoo_message_id
        )
        db.add(db_message)
        
        # Also update the ticket's updated_at timestamp
        db_ticket = await get_ticket_by_id(db, ticket_id)
        if db_ticket:
            db_ticket.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(db_message)
        logger.info(f"Created message for ticket {ticket_id}" + 
                    (f", linked to Odoo message {odoo_message_id}" if odoo_message_id else ""))
        return db_message
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error in create_ticket_message for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_message_by_odoo_id(db: AsyncSession, odoo_message_id: int) -> Optional[TicketMessageORM]:
    """Get a message by its Odoo ID"""
    try:
        result = await db.execute(
            select(TicketMessageORM)
            .where(TicketMessageORM.odoo_message_id == odoo_message_id)
        )
        return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_message_by_odoo_id for Odoo message {odoo_message_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

async def get_ticket_counts_by_status(db: AsyncSession, user_id: int) -> Dict[str, int]:
    """Get count of tickets by status for a user"""
    try:
        # Define statuses we want to count
        statuses = ["new", "in_progress", "solved", "closed"]
        result = {}
        
        # Get total count
        total_query = select(func.count()).select_from(TicketORM).where(TicketORM.user_id == user_id)
        total_result = await db.execute(total_query)
        result["total"] = total_result.scalar()
        
        # Get count for each status
        for status in statuses:
            status_query = select(func.count()).select_from(TicketORM).where(
                TicketORM.user_id == user_id,
                TicketORM.status == status
            )
            status_result = await db.execute(status_query)
            result[status] = status_result.scalar()
        
        return result
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_ticket_counts_by_status for user {user_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise
