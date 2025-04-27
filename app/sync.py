import asyncio
import logging
import re
from datetime import datetime
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models import TicketORM, TicketMessageORM
from app.odoo_manager import odoo_helpdesk

# Set up logging
logger = logging.getLogger("app.sync")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def sync_from_odoo_background():
    """Background task to sync tickets from Odoo"""
    async with AsyncSessionLocal() as db:
        try:
            # Get all tickets with odoo_ticket_id
            result = await db.execute(select(TicketORM).where(TicketORM.odoo_ticket_id.isnot(None)))
            tickets = result.scalars().all()
            
            for ticket in tickets:
                # Get latest from Odoo
                await sync_ticket_from_odoo(db, ticket, ticket.odoo_ticket_id)
            
            await db.commit()
            logger.info(f"Synced {len(tickets)} tickets from Odoo")
        except Exception as e:
            logger.error(f"Background sync failed: {str(e)}")
            await db.rollback()

async def sync_ticket_from_odoo(db: AsyncSession, ticket: TicketORM, odoo_id: int):
    """Sync a single ticket from Odoo to our database"""
    try:
        # Get ticket from Odoo
        odoo_ticket = odoo_helpdesk.get_ticket(odoo_id)
        if not odoo_ticket:
            logger.warning(f"Odoo ticket {odoo_id} not found, might be deleted")
            return
            
        # Update ticket in our database - matching field names with our model
        ticket.title = odoo_ticket.get('name', ticket.title)
        ticket.description = odoo_ticket.get('description', ticket.description)
        ticket.priority = odoo_ticket.get('priority', ticket.priority)
        
        # Update stage
        if odoo_ticket.get('stage_id'):
            new_stage_id = odoo_ticket['stage_id'][0]
            if new_stage_id != ticket.stage_id:
                ticket.stage_id = new_stage_id
                # Map Odoo stage to our statuses
                stage_name = odoo_ticket['stage_id'][1].lower()
                if 'closed' in stage_name:
                    ticket.status = "closed"
                    ticket.is_resolved = True
                elif 'solved' in stage_name or 'done' in stage_name:
                    ticket.status = "solved"
                    ticket.is_resolved = True
                elif 'progress' in stage_name:
                    ticket.status = "in_progress"
                elif 'new' in stage_name:
                    ticket.status = "new"
        
        # Sync messages
        await sync_ticket_messages(db, ticket, odoo_id)
            
        ticket.updated_at = datetime.utcnow()
    except Exception as e:
        logger.error(f"Error syncing ticket {odoo_id}: {str(e)}")
        raise

async def sync_ticket_messages(db: AsyncSession, ticket: TicketORM, odoo_id: int):
    """Sync messages for a ticket from Odoo to our database"""
    try:
        odoo_messages = odoo_helpdesk.get_ticket_messages(odoo_id)
        for odoo_message in odoo_messages:
            # Skip if we already have this message
            result = await db.execute(
                select(TicketMessageORM).where(
                    TicketMessageORM.odoo_message_id == odoo_message['id']
                )
            )
            existing_message = result.scalars().first()
            if existing_message:
                continue
                
            # Skip system messages, only include actual communications
            if not odoo_message.get('body') or len(strip_html_tags(odoo_message['body'])) < 5:
                continue
                
            # Check if message is from support team or user
            is_from_support = True
            # In Odoo, author_id is usually a tuple (id, name)
            if odoo_message.get('author_id') and odoo_message['author_id'][0] == ticket.user_id:
                is_from_support = False
                
            # Create new message
            new_message = TicketMessageORM(
                ticket_id=ticket.id,
                message=strip_html_tags(odoo_message.get('body', '')),
                odoo_message_id=odoo_message['id'],
                is_from_support=is_from_support,
                created_at=datetime.fromisoformat(odoo_message['date'].replace('Z', '+00:00'))
            )
            db.add(new_message)
    except Exception as e:
        logger.error(f"Error syncing messages for ticket {odoo_id}: {str(e)}")

def strip_html_tags(html_text):
    """Remove HTML tags from message body"""
    if not html_text:
        return ""
    # First remove all HTML tags
    text = re.sub('<[^<]+?>', ' ', html_text)
    # Then remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def periodic_sync():
    """Run periodic sync every 5 minutes"""
    while True:
        try:
            logger.info("Starting periodic sync with Odoo")
            await sync_from_odoo_background()
        except Exception as e:
            logger.error(f"Periodic sync error: {str(e)}")
        # Run every 5 minutes
        await asyncio.sleep(300) 