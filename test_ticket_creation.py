import asyncio
import sys
from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.odoo_manager import odoo_helpdesk
from app.crud import create_user, get_user_by_username, create_ticket
from app.models import UserCreate, TicketCreate
from pydantic import EmailStr

async def create_test_ticket():
    async with AsyncSessionLocal() as db:
        # Check if test user exists, create if not
        test_user = await get_user_by_username(db, "testuser")
        if not test_user:
            user_data = UserCreate(
                username="testuser",
                email=EmailStr("testuser@example.com"),
                full_name="Test User",
                password="Test@123"
            )
            test_user = await create_user(db, user_data)
            print(f"Created test user with ID: {test_user.id}")
        else:
            print(f"Using existing test user with ID: {test_user.id}")
        
        # Find partner in Odoo
        print("Finding/creating partner in Odoo...")
        partner_id = odoo_helpdesk.get_or_create_partner(
            "Test User", 
            "testuser@example.com"
        )
        print(f"Partner ID in Odoo: {partner_id}")
        
        # Create ticket in Odoo
        print("Creating ticket in Odoo...")
        odoo_ticket_data = {
            'name': "Test Diagnostic Booking Issue",
            'description': "This is a test ticket to verify integration between app and Odoo",
            'priority': "2",
            'partner_id': partner_id,
        }
        
        try:
            new_odoo_ticket_id = odoo_helpdesk.create_ticket(odoo_ticket_data)
            print(f"Created ticket in Odoo with ID: {new_odoo_ticket_id}")
            
            # Create ticket in our database
            ticket_data = TicketCreate(
                name="Test Diagnostic Booking Issue",
                description="This is a test ticket to verify integration between app and Odoo",
                priority="2",
                user_id=test_user.id
            )
            
            db_ticket = await create_ticket(
                db, 
                ticket_data, 
                test_user.id,
                odoo_id=new_odoo_ticket_id
            )
            
            print(f"Created ticket in database with ID: {db_ticket.id}, linked to Odoo ID: {db_ticket.odoo_ticket_id}")
            
            # Verify we can fetch it from Odoo
            odoo_ticket = odoo_helpdesk.get_ticket(new_odoo_ticket_id)
            print(f"Retrieved ticket from Odoo: {odoo_ticket['name']}")
            
            return True
        except Exception as e:
            print(f"Error creating ticket: {str(e)}")
            return False

if __name__ == "__main__":
    print(f"Using Odoo URL: {settings.ODOO_URL}")
    result = asyncio.run(create_test_ticket())
    if result:
        print("✅ Test completed successfully. Check your Odoo helpdesk dashboard.")
        sys.exit(0)
    else:
        print("❌ Test failed. See error messages above.")
        sys.exit(1) 