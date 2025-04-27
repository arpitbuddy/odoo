from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserORM, TicketORM, TicketMessageORM
from app.schemas import UserCreate, TicketCreate, Ticket, TicketMessageCreate
from app.utils import get_password_hash
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy import func

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(UserORM).where(UserORM.email == email))
    return result.scalars().first()

async def get_user_by_username(db: AsyncSession, username: str):
    result = await db.execute(select(UserORM).where(UserORM.username == username))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: UserCreate):
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
    return db_user

# Ticket operations
async def get_tickets_by_user_id(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(TicketORM)
        .where(TicketORM.user_id == user_id)
        .order_by(TicketORM.created_at.desc())
    )
    return result.scalars().all()

async def get_filtered_tickets(
    db: AsyncSession, 
    user_id: int, 
    status: Optional[str] = None, 
    priority: Optional[str] = None
):
    """Get tickets filtered by status and priority"""
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

async def get_ticket_by_id(db: AsyncSession, ticket_id: int):
    result = await db.execute(select(TicketORM).where(TicketORM.id == ticket_id))
    return result.scalars().first()

async def get_ticket_by_odoo_id(db: AsyncSession, odoo_id: int):
    result = await db.execute(select(TicketORM).where(TicketORM.odoo_ticket_id == odoo_id))
    return result.scalars().first()

async def create_ticket(db: AsyncSession, ticket: TicketCreate, user_id: int, odoo_id: int = None):
    """Create a ticket in the database with optional Odoo ID"""
    db_ticket = TicketORM(
        title=ticket.name,
        description=ticket.description,
        priority=ticket.priority,
        user_id=user_id,
        odoo_ticket_id=odoo_id,
        status="new",
    )
    db.add(db_ticket)
    await db.commit()
    await db.refresh(db_ticket)
    return db_ticket

async def update_ticket(db: AsyncSession, ticket_id: int, ticket_data: dict):
    """Update a ticket with dictionary of values"""
    db_ticket = await get_ticket_by_id(db, ticket_id)
    if db_ticket is None:
        return None
        
    for key, value in ticket_data.items():
        setattr(db_ticket, key, value)
        
    await db.commit()
    await db.refresh(db_ticket)
    return db_ticket

async def delete_ticket(db: AsyncSession, ticket_id: int):
    """Delete a ticket by ID"""
    db_ticket = await get_ticket_by_id(db, ticket_id)
    if db_ticket is None:
        return None
    await db.delete(db_ticket)
    await db.commit()
    return db_ticket

# Ticket message operations
async def get_ticket_messages(db: AsyncSession, ticket_id: int):
    """Get all messages for a ticket"""
    result = await db.execute(
        select(TicketMessageORM)
        .where(TicketMessageORM.ticket_id == ticket_id)
        .order_by(TicketMessageORM.created_at)
    )
    return result.scalars().all()

async def create_ticket_message(db: AsyncSession, ticket_id: int, message: str, is_from_support: bool = False, odoo_message_id: int = None):
    """Create a new message for a ticket"""
    db_message = TicketMessageORM(
        ticket_id=ticket_id,
        message=message,
        is_from_support=is_from_support,
        odoo_message_id=odoo_message_id
    )
    db.add(db_message)
    
    # Also update the ticket's updated_at timestamp
    db_ticket = await get_ticket_by_id(db, ticket_id)
    
    await db.commit()
    await db.refresh(db_message)
    return db_message

async def get_message_by_odoo_id(db: AsyncSession, odoo_message_id: int):
    """Get a message by its Odoo ID"""
    result = await db.execute(
        select(TicketMessageORM)
        .where(TicketMessageORM.odoo_message_id == odoo_message_id)
    )
    return result.scalars().first()

async def get_ticket_counts_by_status(db: AsyncSession, user_id: int) -> Dict[str, int]:
    """Get count of tickets by status for a user"""
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
