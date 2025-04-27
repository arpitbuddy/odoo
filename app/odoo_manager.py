import xmlrpc.client
import logging
import traceback
from app.config import settings
from typing import Any, Dict, List, Optional, Union
import time

# Set up logging
logger = logging.getLogger("app.odoo")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

class OdooError(Exception):
    """Custom exception for Odoo API errors"""
    pass

class OdooHelpdeskManager:
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.common_proxy = None
        self.object_proxy = None
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        self.connect()
    
    def connect(self) -> bool:
        """Establish connection to Odoo"""
        try:
            logger.info(f"Connecting to Odoo at {self.url}")
            self.common_proxy = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            self.uid = self.common_proxy.authenticate(self.db, self.username, self.password, {})
            if not self.uid:
                error_msg = "Authentication with Odoo failed: Invalid credentials or database"
                logger.error(error_msg)
                raise ValueError(error_msg)
            self.object_proxy = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
            logger.info(f"Connected to Odoo at {self.url} (user ID: {self.uid})")
            return True
        except xmlrpc.client.Fault as e:
            logger.error(f"Odoo XML-RPC fault: {e.faultCode} - {e.faultString}")
            logger.debug(traceback.format_exc())
            return False
        except xmlrpc.client.ProtocolError as e:
            logger.error(f"Odoo protocol error: {e.errcode} - {e.errmsg}")
            logger.debug(traceback.format_exc())
            return False
        except Exception as e:
            logger.error(f"Odoo connection failed: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
    
    def execute_kw(self, model: str, method: str, args: List, kwargs: Optional[Dict] = None) -> Any:
        """Execute Odoo method with retry logic"""
        if not kwargs:
            kwargs = {}
        
        # Make sure we have a valid connection
        if not self.uid or not self.object_proxy:
            if not self.connect():
                raise OdooError("Not connected to Odoo")
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Executing {model}.{method} (attempt {attempt}/{self.max_retries})")
                result = self.object_proxy.execute_kw(
                    self.db, self.uid, self.password,
                    model, method, args, kwargs
                )
                return result
            except xmlrpc.client.Fault as e:
                error_msg = f"Odoo XML-RPC fault: {e.faultCode} - {e.faultString}"
                logger.error(error_msg)
                logger.debug(traceback.format_exc())
                
                # Don't retry on permission errors or record not found
                if "Access" in e.faultString or "does not exist" in e.faultString:
                    raise OdooError(error_msg)
                
                if attempt == self.max_retries:
                    raise OdooError(error_msg)
            except xmlrpc.client.ProtocolError as e:
                error_msg = f"Odoo protocol error: {e.errcode} - {e.errmsg}"
                logger.error(error_msg)
                logger.debug(traceback.format_exc())
                
                if attempt == self.max_retries:
                    raise OdooError(error_msg)
            except Exception as e:
                error_msg = f"Odoo operation failed: {str(e)}"
                logger.error(error_msg)
                logger.debug(traceback.format_exc())
                
                # Try to reconnect
                if attempt < self.max_retries:
                    logger.info(f"Attempting to reconnect (attempt {attempt}/{self.max_retries})")
                    self.connect()
                else:
                    raise OdooError(error_msg)
            
            # Wait before retrying
            time.sleep(self.retry_delay)
    
    # Helpdesk specific methods
    def create_ticket(self, ticket_data: Dict) -> int:
        """Create a new helpdesk ticket in Odoo"""
        try:
            ticket_id = self.execute_kw(
                'helpdesk.ticket', 'create',
                [ticket_data]
            )
            logger.info(f"Created Odoo ticket #{ticket_id} with data: {ticket_data.get('name')}")
            return ticket_id
        except Exception as e:
            error_msg = f"Failed to create ticket in Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Ticket data: {ticket_data}")
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)
    
    def update_ticket(self, odoo_id: int, ticket_data: Dict) -> bool:
        """Update an existing helpdesk ticket in Odoo"""
        try:
            result = self.execute_kw(
                'helpdesk.ticket', 'write',
                [[odoo_id], ticket_data]
            )
            logger.info(f"Updated Odoo ticket #{odoo_id} with fields: {list(ticket_data.keys())}")
            return result
        except Exception as e:
            error_msg = f"Failed to update ticket #{odoo_id} in Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Update data: {ticket_data}")
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)
    
    def get_ticket(self, odoo_id: int) -> Optional[Dict]:
        """Get a single ticket by ID"""
        try:
            tickets = self.execute_kw(
                'helpdesk.ticket', 'read',
                [[odoo_id]]
            )
            result = tickets[0] if tickets else None
            if not result:
                logger.warning(f"Ticket #{odoo_id} not found in Odoo")
            return result
        except Exception as e:
            error_msg = f"Failed to get ticket #{odoo_id} from Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            # Don't raise here as this is often used in syncing
            return None
    
    def get_tickets(self, domain: Optional[List] = None, fields: Optional[List] = None) -> List[Dict]:
        """Get tickets with optional domain and fields"""
        try:
            if domain is None:
                domain = []
            if fields is None:
                fields = ['name', 'description', 'priority', 'stage_id', 'partner_id']
                
            tickets = self.execute_kw(
                'helpdesk.ticket', 'search_read',
                [domain],
                {'fields': fields}
            )
            logger.info(f"Retrieved {len(tickets)} tickets from Odoo matching domain: {domain}")
            return tickets
        except Exception as e:
            error_msg = f"Failed to get tickets from Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Domain: {domain}, Fields: {fields}")
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)
    
    def get_ticket_messages(self, odoo_ticket_id: int) -> List[Dict]:
        """Get messages for a ticket"""
        try:
            message_ids = self.execute_kw(
                'mail.message', 'search',
                [[
                    ('model', '=', 'helpdesk.ticket'),
                    ('res_id', '=', odoo_ticket_id)
                ]]
            )
            
            if not message_ids:
                logger.debug(f"No messages found for ticket #{odoo_ticket_id}")
                return []
                
            messages = self.execute_kw(
                'mail.message', 'read',
                [message_ids],
                {'fields': ['body', 'date', 'author_id']}
            )
            logger.debug(f"Retrieved {len(messages)} messages for ticket #{odoo_ticket_id}")
            return messages
        except Exception as e:
            error_msg = f"Failed to get messages for ticket #{odoo_ticket_id} from Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            # Don't raise here as this is often used in syncing
            return []
    
    def add_message_to_ticket(self, odoo_ticket_id: int, message_body: str, author_name: Optional[str] = None) -> int:
        """Add a message to a ticket"""
        try:
            result = self.execute_kw(
                'helpdesk.ticket', 'message_post',
                [[odoo_ticket_id]],
                {
                    'body': message_body,
                    'message_type': 'comment',
                    'subtype': 'mail.mt_comment'
                }
            )
            logger.info(f"Added message to ticket #{odoo_ticket_id}")
            return result
        except Exception as e:
            error_msg = f"Failed to add message to ticket #{odoo_ticket_id} in Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)
    
    def get_ticket_stages(self) -> List[Dict]:
        """Get all available ticket stages"""
        try:
            stage_ids = self.execute_kw(
                'helpdesk.stage', 'search',
                [[]]
            )
            
            stages = self.execute_kw(
                'helpdesk.stage', 'read',
                [stage_ids],
                {'fields': ['id', 'name', 'sequence']}
            )
            logger.info(f"Retrieved {len(stages)} ticket stages from Odoo")
            return stages
        except Exception as e:
            error_msg = f"Failed to get ticket stages from Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)
        
    def get_or_create_partner(self, name: str, email: str) -> int:
        """Find or create a partner in Odoo"""
        try:
            partners = self.execute_kw(
                'res.partner', 'search_read',
                [[['email', '=', email]]],
                {'fields': ['id', 'name', 'email']}
            )
            
            if partners:
                logger.info(f"Found existing Odoo partner for email {email}: ID {partners[0]['id']}")
                return partners[0]['id']
                
            # Create new partner
            partner_data = {
                'name': name,
                'email': email,
                'customer': True,
            }
            
            partner_id = self.execute_kw(
                'res.partner', 'create',
                [partner_data]
            )
            logger.info(f"Created new Odoo partner for {name} <{email}> with ID {partner_id}")
            return partner_id
        except Exception as e:
            error_msg = f"Failed to get or create partner in Odoo: {str(e)}"
            logger.error(error_msg)
            logger.debug(traceback.format_exc())
            raise OdooError(error_msg)

# Initialize once at app startup
try:
    odoo_helpdesk = OdooHelpdeskManager(
        settings.ODOO_URL,
        settings.ODOO_DB,
        settings.ODOO_USERNAME,
        settings.ODOO_PASSWORD
    )
except Exception as e:
    logger.critical(f"Failed to initialize Odoo Helpdesk Manager: {str(e)}")
    logger.critical(traceback.format_exc())
    # Create a dummy manager that will log errors but not crash the app
    odoo_helpdesk = None 