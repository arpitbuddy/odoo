import asyncio
import sys
from app.config import settings
from app.database import AsyncSessionLocal
from app.odoo_manager import odoo_helpdesk
from app.crud import get_ticket_by_id
from app.sync import sync_ticket_from_odoo, sync_ticket_messages

async def check_ticket_updates():
    # Use the ticket ID created in the previous test
    ticket_id = 2
    
    async with AsyncSessionLocal() as db:
        # Get ticket from our database
        db_ticket = await get_ticket_by_id(db, ticket_id)
        if not db_ticket:
            print(f"❌ Ticket with ID {ticket_id} not found in database")
            return False
            
        print(f"Found ticket: {db_ticket.title} (ID: {db_ticket.id}, Odoo ID: {db_ticket.odoo_ticket_id})")
        print(f"Current status: {db_ticket.status}")
        
        # Get direct from Odoo to compare
        odoo_ticket = odoo_helpdesk.get_ticket(db_ticket.odoo_ticket_id)
        if not odoo_ticket:
            print(f"❌ Ticket with Odoo ID {db_ticket.odoo_ticket_id} not found in Odoo")
            return False
            
        print(f"Odoo ticket: {odoo_ticket['name']}")
        print(f"Odoo stage: {odoo_ticket['stage_id'][1]}")
        
        # Sync any changes
        print("\nSyncing ticket from Odoo...")
        await sync_ticket_from_odoo(db, db_ticket, db_ticket.odoo_ticket_id)
        await sync_ticket_messages(db, db_ticket, db_ticket.odoo_ticket_id)
        await db.commit()
        
        # Check if anything changed
        db_ticket = await get_ticket_by_id(db, ticket_id)
        print(f"After sync - Status: {db_ticket.status}")
        
        # Get messages
        odoo_messages = odoo_helpdesk.get_ticket_messages(db_ticket.odoo_ticket_id)
        print(f"\nFound {len(odoo_messages)} messages in Odoo")
        
        for i, msg in enumerate(odoo_messages[:5]):  # Show first 5 messages only
            print(f"Message {i+1}: {msg.get('body', '')[:100]}...")
        
        return True

if __name__ == "__main__":
    print(f"Using Odoo URL: {settings.ODOO_URL}")
    result = asyncio.run(check_ticket_updates())
    if result:
        print("\n✅ Ticket check completed. The integration is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Ticket check failed. See error messages above.")
        sys.exit(1) 