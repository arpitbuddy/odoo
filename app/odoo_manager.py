import xmlrpc.client
import logging
from app.config import settings

# Set up logging
logger = logging.getLogger("app.odoo")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

class OdooHelpdeskManager:
    def __init__(self, url, db, username, password):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.common_proxy = None
        self.object_proxy = None
        self.connect()
    
    def connect(self):
        """Establish connection to Odoo"""
        try:
            self.common_proxy = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            self.uid = self.common_proxy.authenticate(self.db, self.username, self.password, {})
            if not self.uid:
                raise ValueError("Authentication with Odoo failed")
            self.object_proxy = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
            logger.info(f"Connected to Odoo at {self.url}")
            return True
        except Exception as e:
            logger.error(f"Odoo connection failed: {str(e)}")
            return False
    
    def execute_kw(self, model, method, args, kwargs=None):
        """Execute Odoo method with reconnection logic"""
        if not kwargs:
            kwargs = {}
        
        try:
            return self.object_proxy.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
        except Exception as e:
            # Try to reconnect once
            logger.warning(f"Odoo operation failed, attempting reconnect: {str(e)}")
            if self.connect():
                return self.object_proxy.execute_kw(
                    self.db, self.uid, self.password,
                    model, method, args, kwargs
                )
            else:
                logger.error(f"Reconnection failed: {str(e)}")
                raise ConnectionError(f"Failed to reconnect to Odoo: {str(e)}")
    
    # Helpdesk specific methods
    def create_ticket(self, ticket_data):
        """Create a new helpdesk ticket in Odoo"""
        return self.execute_kw(
            'helpdesk.ticket', 'create',
            [ticket_data]
        )
    
    def update_ticket(self, odoo_id, ticket_data):
        """Update an existing helpdesk ticket in Odoo"""
        return self.execute_kw(
            'helpdesk.ticket', 'write',
            [[odoo_id], ticket_data]
        )
    
    def get_ticket(self, odoo_id):
        """Get a single ticket by ID"""
        tickets = self.execute_kw(
            'helpdesk.ticket', 'read',
            [[odoo_id]]
        )
        return tickets[0] if tickets else None
    
    def get_tickets(self, domain=None, fields=None):
        """Get tickets with optional domain and fields"""
        if domain is None:
            domain = []
        if fields is None:
            fields = ['name', 'description', 'priority', 'stage_id', 'partner_id']
            
        return self.execute_kw(
            'helpdesk.ticket', 'search_read',
            [domain],
            {'fields': fields}
        )
    
    def get_ticket_messages(self, odoo_ticket_id):
        """Get messages for a ticket"""
        message_ids = self.execute_kw(
            'mail.message', 'search',
            [[
                ('model', '=', 'helpdesk.ticket'),
                ('res_id', '=', odoo_ticket_id)
            ]]
        )
        
        if not message_ids:
            return []
            
        return self.execute_kw(
            'mail.message', 'read',
            [message_ids],
            {'fields': ['body', 'date', 'author_id']}
        )
    
    def add_message_to_ticket(self, odoo_ticket_id, message_body, author_name=None):
        """Add a message to a ticket"""
        return self.execute_kw(
            'helpdesk.ticket', 'message_post',
            [[odoo_ticket_id]],
            {
                'body': message_body,
                'message_type': 'comment',
                'subtype': 'mail.mt_comment'
            }
        )
    
    def get_ticket_stages(self):
        """Get all available ticket stages"""
        stage_ids = self.execute_kw(
            'helpdesk.stage', 'search',
            [[]]
        )
        
        return self.execute_kw(
            'helpdesk.stage', 'read',
            [stage_ids],
            {'fields': ['id', 'name', 'sequence']}
        )
        
    def get_or_create_partner(self, name, email):
        """Find or create a partner in Odoo"""
        partners = self.execute_kw(
            'res.partner', 'search_read',
            [[['email', '=', email]]],
            {'fields': ['id', 'name', 'email']}
        )
        
        if partners:
            return partners[0]['id']
            
        # Create new partner
        partner_data = {
            'name': name,
            'email': email,
            'customer': True,
        }
        
        return self.execute_kw(
            'res.partner', 'create',
            [partner_data]
        )

# Initialize once at app startup
odoo_helpdesk = OdooHelpdeskManager(
    settings.ODOO_URL,
    settings.ODOO_DB,
    settings.ODOO_USERNAME,
    settings.ODOO_PASSWORD
) 