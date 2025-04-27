from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app import models, schemas, crud
from app.config import settings
from app.dependencies import get_current_user, get_db
from app.database import AsyncSession
from app.odoo_manager import odoo_helpdesk
from app.sync import sync_ticket_from_odoo, sync_ticket_messages
from typing import List, Optional
import logging

# Set up logging
logger = logging.getLogger("app.routers.tickets")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

router = APIRouter()

@router.get("/", response_model=List[schemas.Ticket])
async def get_tickets(
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Get all tickets for the current user directly from PostgreSQL"""
    try:
        # Fetch tickets directly from our database
        db_user_tickets = await crud.get_tickets_by_user_id(db, current_user.id)
        return db_user_tickets
    except Exception as e:
        logger.error(f"Error getting tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/filter", response_model=List[schemas.Ticket])
async def filter_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for the current user filtered by status and/or priority"""
    try:
        # Fetch tickets with filters
        db_user_tickets = await crud.get_filtered_tickets(
            db, 
            user_id=current_user.id,
            status=status,
            priority=priority
        )
        return db_user_tickets
    except Exception as e:
        logger.error(f"Error filtering tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/count", response_model=schemas.TicketStatusCount)
async def get_ticket_counts(
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Get count of tickets by status for the current user"""
    try:
        # Get counts by status
        counts = await crud.get_ticket_counts_by_status(db, current_user.id)
        
        # Create response object
        return schemas.TicketStatusCount(
            new=counts["new"],
            in_progress=counts["in_progress"],
            solved=counts["solved"],
            closed=counts["closed"],
            total=counts["total"]
        )
    except Exception as e:
        logger.error(f"Error getting ticket counts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/statuses", response_model=schemas.TicketStatuses)
async def get_ticket_statuses():
    """Get all possible ticket statuses"""
    try:
        # Define all possible statuses
        statuses = [
            {"id": "new", "name": "New"},
            {"id": "in_progress", "name": "In Progress"},
            {"id": "solved", "name": "Solved"},
            {"id": "closed", "name": "Closed"}
        ]
        
        return {"statuses": statuses}
    except Exception as e:
        logger.error(f"Error getting ticket statuses: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync", response_model=dict)
async def sync_tickets(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Trigger sync from Odoo to update local database"""
    try:
        # Start sync in background
        background_tasks.add_task(sync_tickets_for_user, db, current_user)
        return {"status": "Sync started in background"}
    except Exception as e:
        logger.error(f"Error starting sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def sync_tickets_for_user(db: AsyncSession, current_user: models.User):
    """Sync tickets for a specific user"""
    try:
        # Find partner_id for this user
        partner_id = await get_partner_id_for_user(current_user)
        if not partner_id:
            logger.warning(f"No Odoo partner found for user {current_user.username}")
            return
            
        # Get tickets from Odoo for this partner
        odoo_tickets = odoo_helpdesk.get_tickets(
            domain=[('partner_id', '=', partner_id)],
            fields=['name', 'description', 'priority', 'stage_id', 'partner_id']
        )
        
        # Sync each ticket
        for odoo_ticket in odoo_tickets:
            # Check if we already have this ticket
            db_ticket = await crud.get_ticket_by_odoo_id(db, odoo_ticket['id'])
            if db_ticket:
                # Update existing ticket
                await sync_ticket_from_odoo(db, db_ticket, odoo_ticket['id'])
            else:
                # Create new ticket
                new_ticket = models.TicketCreate(
                    name=odoo_ticket['name'],
                    description=odoo_ticket.get('description', ''),
                    priority=odoo_ticket.get('priority', '1'),
                    user_id=current_user.id
                )
                db_ticket = await crud.create_ticket(
                    db, 
                    new_ticket, 
                    current_user.id, 
                    odoo_ticket_id=odoo_ticket['id']
                )
                
                # Sync messages for the new ticket
                await sync_ticket_messages(db, db_ticket, odoo_ticket['id'])
        
        await db.commit()
        logger.info(f"Synced {len(odoo_tickets)} tickets for user {current_user.username}")
    except Exception as e:
        logger.error(f"Error syncing tickets for user: {str(e)}")
        await db.rollback()

@router.post("/", response_model=schemas.Ticket)
async def create_ticket(
    ticket: schemas.TicketCreate, 
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Create a new support ticket in both Odoo and PostgreSQL"""
    try:
        # Find or create partner in Odoo
        partner_id = await get_partner_id_for_user(current_user)
        
        # Prepare data for Odoo
        odoo_ticket_data = {
            'name': ticket.name,
            'description': ticket.description,
            'priority': ticket.priority,
            'partner_id': partner_id,
        }
        
        # Add optional fields if they exist
        if ticket.diagnostic_test_id:
            odoo_ticket_data['x_diagnostic_test'] = str(ticket.diagnostic_test_id)
        if ticket.lab_id:
            odoo_ticket_data['x_lab'] = str(ticket.lab_id)
        if ticket.booking_id:
            odoo_ticket_data['x_booking_ref'] = str(ticket.booking_id)
        
        # Create in Odoo first
        try:
            new_odoo_ticket_id = odoo_helpdesk.create_ticket(odoo_ticket_data)
            logger.info(f"Created ticket {new_odoo_ticket_id} in Odoo")
        except Exception as e:
            logger.error(f"Failed to create ticket in Odoo: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create ticket in Odoo: {str(e)}")
        
        # Create in PostgreSQL
        db_ticket = await crud.create_ticket(
            db, 
            ticket, 
            current_user.id,
            odoo_ticket_id=new_odoo_ticket_id
        )
        
        return db_ticket
    except Exception as e:
        logger.error(f"Error creating ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{ticket_id}", response_model=schemas.TicketDetail)
async def get_ticket_detail(
    ticket_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a ticket including messages"""
    try:
        # Get the ticket
        db_ticket = await crud.get_ticket_by_id(db, ticket_id)
        if not db_ticket or db_ticket.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        # If we have an odoo_ticket_id, try to sync latest state
        if db_ticket.odoo_ticket_id:
            try:
                await sync_ticket_from_odoo(db, db_ticket, db_ticket.odoo_ticket_id)
                await db.commit()
                # Refresh after sync
                db_ticket = await crud.get_ticket_by_id(db, ticket_id)
            except Exception as e:
                logger.warning(f"Could not sync ticket {ticket_id} from Odoo: {str(e)}")
                # Continue anyway
                
        # Get messages
        messages = await crud.get_ticket_messages(db, ticket_id)
        
        # Create response
        ticket_detail = schemas.TicketDetail.from_orm(db_ticket)
        ticket_detail.messages = [schemas.TicketMessage.from_orm(msg) for msg in messages]
        
        return ticket_detail
    except Exception as e:
        logger.error(f"Error getting ticket detail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{ticket_id}/messages", response_model=schemas.TicketMessage)
async def add_message(
    ticket_id: int,
    message: schemas.TicketMessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a message to a ticket"""
    try:
        # Check if ticket exists and belongs to user
        db_ticket = await crud.get_ticket_by_id(db, ticket_id)
        if not db_ticket or db_ticket.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        # If we have an odoo_ticket_id, add message there first
        odoo_message_id = None
        if db_ticket.odoo_ticket_id:
            try:
                message_text = f"{message.message}\n\n- Sent by {current_user.full_name or current_user.username} from mobile app"
                odoo_message_id = odoo_helpdesk.add_message_to_ticket(
                    db_ticket.odoo_ticket_id,
                    message_text
                )
                logger.info(f"Added message to Odoo ticket {db_ticket.odoo_ticket_id}")
            except Exception as e:
                logger.error(f"Failed to add message to Odoo: {str(e)}")
                # Continue anyway - at least save in our database
        
        # Add message to our database
        db_message = await crud.create_ticket_message(
            db, 
            ticket_id, 
            message.message,
            is_from_support=False,
            odoo_message_id=odoo_message_id
        )
        
        return schemas.TicketMessage.from_orm(db_message)
    except Exception as e:
        logger.error(f"Error adding message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{ticket_id}", response_model=schemas.Ticket)
async def update_ticket(
    ticket_id: int, 
    ticket: schemas.TicketCreate, 
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Update a ticket in both Odoo and PostgreSQL"""
    try:
        # Check if ticket exists and belongs to user
        db_ticket = await crud.get_ticket_by_id(db, ticket_id)
        if not db_ticket or db_ticket.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        # If we have an odoo_ticket_id, update in Odoo first
        if db_ticket.odoo_ticket_id:
            # Prepare update data
            odoo_update_data = {
                'name': ticket.name,
                'description': ticket.description,
                'priority': ticket.priority,
            }
            
            # Update optional fields if they exist
            if ticket.diagnostic_test_id:
                odoo_update_data['x_diagnostic_test'] = str(ticket.diagnostic_test_id)
            if ticket.lab_id:
                odoo_update_data['x_lab'] = str(ticket.lab_id)
            if ticket.booking_id:
                odoo_update_data['x_booking_ref'] = str(ticket.booking_id)
            
            try:
                odoo_helpdesk.update_ticket(db_ticket.odoo_ticket_id, odoo_update_data)
                logger.info(f"Updated ticket {db_ticket.odoo_ticket_id} in Odoo")
            except Exception as e:
                logger.error(f"Failed to update ticket in Odoo: {str(e)}")
                # Continue anyway - at least update our database
        
        # Update in PostgreSQL
        update_data = {
            'name': ticket.name,
            'description': ticket.description,
            'priority': ticket.priority,
            'diagnostic_test_id': ticket.diagnostic_test_id,
            'lab_id': ticket.lab_id,
            'booking_id': ticket.booking_id,
        }
        
        updated_ticket = await crud.update_ticket(db, ticket_id, update_data)
        return updated_ticket
    except Exception as e:
        logger.error(f"Error updating ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: int, 
    current_user: models.User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Delete a ticket from both Odoo and PostgreSQL"""
    try:
        # Check if ticket exists and belongs to user
        db_ticket = await crud.get_ticket_by_id(db, ticket_id)
        if not db_ticket or db_ticket.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        # If we have an odoo_ticket_id, delete from Odoo first
        if db_ticket.odoo_ticket_id:
            try:
                odoo_helpdesk.execute_kw('helpdesk.ticket', 'unlink', [[db_ticket.odoo_ticket_id]])
                logger.info(f"Deleted ticket {db_ticket.odoo_ticket_id} from Odoo")
            except Exception as e:
                logger.error(f"Failed to delete ticket from Odoo: {str(e)}")
                # Continue anyway - at least delete from our database
        
        # Delete from PostgreSQL
        await crud.delete_ticket(db, ticket_id)
        return None
    except Exception as e:
        logger.error(f"Error deleting ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_partner_id_for_user(user: models.User):
    """Find or create a partner in Odoo for a user"""
    try:
        name = user.full_name or user.username
        return odoo_helpdesk.get_or_create_partner(name, user.email)
    except Exception as e:
        logger.error(f"Error getting partner ID: {str(e)}")
        # Return a default value rather than failing
        return False
