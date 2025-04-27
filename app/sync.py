import asyncio
import logging
import re
import traceback
from datetime import datetime
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.database import AsyncSessionLocal
from app.models import TicketORM, TicketMessageORM
from app.odoo_manager import odoo_helpdesk, OdooError

# Set up logging
logger = logging.getLogger("app.sync")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def sync_from_odoo_background():
    """Background task to sync tickets from Odoo"""
    if odoo_helpdesk is None:
        logger.error("Cannot sync from Odoo: Odoo connection not available")
        return
        
    async with AsyncSessionLocal() as db:
        try:
            # Get all tickets with odoo_ticket_id
            result = await db.execute(select(TicketORM).where(TicketORM.odoo_ticket_id.isnot(None)))
            tickets = result.scalars().all()
            
            if not tickets:
                logger.info("No tickets to sync from Odoo")
                return
                
            successful_syncs = 0
            for ticket in tickets:
                try:
                    # Get latest from Odoo
                    await sync_ticket_from_odoo(db, ticket, ticket.odoo_ticket_id)
                    successful_syncs += 1
                except Exception as e:
                    logger.error(f"Failed to sync ticket {ticket.id} (Odoo ID: {ticket.odoo_ticket_id}): {str(e)}")
                    logger.debug(traceback.format_exc())
                    # Continue with other tickets
            
            await db.commit()
            logger.info(f"Synced {successful_syncs}/{len(tickets)} tickets from Odoo")
        except SQLAlchemyError as e:
            logger.error(f"Database error during background sync: {str(e)}")
            logger.error(traceback.format_exc())
            await db.rollback()
        except Exception as e:
            logger.error(f"Background sync failed: {str(e)}")
            logger.error(traceback.format_exc())
            await db.rollback()

async def sync_ticket_from_odoo(db: AsyncSession, ticket: TicketORM, odoo_id: int):
    """Sync a single ticket from Odoo to our database"""
    if odoo_helpdesk is None:
        logger.error("Cannot sync ticket from Odoo: Odoo connection not available")
        return
        
    try:
        # Get ticket from Odoo
        odoo_ticket = odoo_helpdesk.get_ticket(odoo_id)
        if not odoo_ticket:
            logger.warning(f"Odoo ticket {odoo_id} not found, might be deleted")
            return
            
        # Log the fields we're updating
        logger.debug(f"Syncing ticket {ticket.id} (Odoo ID: {odoo_id}) from Odoo")
            
        # Update ticket in our database - matching field names with our model
        ticket.title = odoo_ticket.get('name', ticket.title)
        ticket.description = odoo_ticket.get('description', ticket.description)
        ticket.priority = odoo_ticket.get('priority', ticket.priority)
        
        # Update stage
        if odoo_ticket.get('stage_id'):
            new_stage_id = odoo_ticket['stage_id'][0]
            old_stage_id = ticket.stage_id
            old_status = ticket.status
            
            if new_stage_id != old_stage_id:
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
                    
                # Log the status change
                if old_status != ticket.status:
                    logger.info(
                        f"Ticket {ticket.id} status changed: {old_status} -> {ticket.status} "
                        f"(Odoo stage: {odoo_ticket['stage_id'][1]})"
                    )
        
        # Sync messages
        await sync_ticket_messages(db, ticket, odoo_id)
            
        ticket.updated_at = datetime.utcnow()
        logger.debug(f"Successfully synced ticket {ticket.id} from Odoo")
    except OdooError as e:
        logger.error(f"Odoo error syncing ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error syncing ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"Error syncing ticket {odoo_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise

async def sync_ticket_messages(db: AsyncSession, ticket: TicketORM, odoo_id: int):
    """Sync messages for a ticket from Odoo to our database"""
    if odoo_helpdesk is None:
        logger.error("Cannot sync messages from Odoo: Odoo connection not available")
        return
        
    try:
        odoo_messages = odoo_helpdesk.get_ticket_messages(odoo_id)
        
        new_messages_count = 0
        for odoo_message in odoo_messages:
            try:
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
                new_messages_count += 1
            except Exception as e:
                logger.error(f"Error processing message {odoo_message.get('id')} for ticket {odoo_id}: {str(e)}")
                logger.debug(traceback.format_exc())
                # Continue with other messages
        
        if new_messages_count > 0:
            logger.info(f"Added {new_messages_count} new messages for ticket {ticket.id}")
    except OdooError as e:
        logger.error(f"Odoo error syncing messages for ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())
    except SQLAlchemyError as e:
        logger.error(f"Database error syncing messages for ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        raise
    except Exception as e:
        logger.error(f"Error syncing messages for ticket {odoo_id}: {str(e)}")
        logger.debug(traceback.format_exc())

def strip_html_tags(html_text):
    """Remove HTML tags from message body"""
    if not html_text:
        return ""
    try:
        # First remove all HTML tags
        text = re.sub('<[^<]+?>', ' ', html_text)
        # Then remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        logger.error(f"Error stripping HTML tags: {str(e)}")
        logger.debug(traceback.format_exc())
        # Return original if we can't parse it
        return html_text

async def periodic_sync():
    """Run periodic sync every 5 minutes"""
    while True:
        try:
            logger.info("Starting periodic sync with Odoo")
            await sync_from_odoo_background()
        except Exception as e:
            logger.error(f"Periodic sync error: {str(e)}")
            logger.error(traceback.format_exc())
        
        try:
            # Run every 5 minutes
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Periodic sync task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic sync sleep: {str(e)}")
            logger.error(traceback.format_exc())
            # Still try to sleep to avoid tight loop
            await asyncio.sleep(60)

async def sync_messages_from_odoo(db: AsyncSession, ticket_id: int):
    """Sync messages for a specific ticket from Odoo"""
    try:
        # Get the ticket
        result = await db.execute(select(TicketORM).where(TicketORM.id == ticket_id))
        ticket = result.scalars().first()
        
        if not ticket or not ticket.odoo_ticket_id:
            logger.warning(f"Cannot sync messages: Ticket {ticket_id} not found or has no Odoo ID")
            return
            
        # Use the existing sync_ticket_messages function
        await sync_ticket_messages(db, ticket, ticket.odoo_ticket_id)
        
        # Update ticket timestamp
        ticket.updated_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"Successfully synced messages for ticket {ticket_id} from Odoo")
    except SQLAlchemyError as e:
        logger.error(f"Database error syncing messages for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error syncing messages for ticket {ticket_id}: {str(e)}")
        logger.debug(traceback.format_exc())
        await db.rollback()
        raise

async def sync_all_tickets(db: AsyncSession):
    """Sync all tickets from Odoo"""
    if odoo_helpdesk is None:
        logger.error("Cannot sync tickets from Odoo: Odoo connection not available")
        return
        
    try:
        # Get all tickets from Odoo
        odoo_tickets = odoo_helpdesk.get_all_tickets()
        
        if not odoo_tickets:
            logger.info("No tickets found in Odoo")
            return
            
        # Process each Odoo ticket
        for odoo_ticket in odoo_tickets:
            try:
                odoo_id = odoo_ticket.get('id')
                if not odoo_id:
                    continue
                    
                # Check if we already have this ticket
                result = await db.execute(
                    select(TicketORM).where(TicketORM.odoo_ticket_id == odoo_id)
                )
                ticket = result.scalars().first()
                
                if ticket:
                    # Update existing ticket
                    await sync_ticket_from_odoo(db, ticket, odoo_id)
                else:
                    # Create new ticket (simplified, would need user_id in real implementation)
                    logger.info(f"Found new ticket in Odoo: {odoo_id} - {odoo_ticket.get('name')}")
                    # Would create a new ticket here but we need more context
            except Exception as e:
                logger.error(f"Error processing Odoo ticket {odoo_ticket.get('id')}: {str(e)}")
                logger.debug(traceback.format_exc())
                # Continue with other tickets
        
        await db.commit()
        logger.info(f"Completed syncing all tickets from Odoo")
    except SQLAlchemyError as e:
        logger.error(f"Database error during sync_all_tickets: {str(e)}")
        logger.debug(traceback.format_exc())
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error during sync_all_tickets: {str(e)}")
        logger.debug(traceback.format_exc())
        await db.rollback()
        raise 