# Healthcare Call Center Support Ticket System

## Overview
This project integrates Odoo's Helpdesk module with a FastAPI backend to manage support tickets for a call center team.

## Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-repo/healthcare_app.git
   cd healthcare_app
   ```

2. **Create a Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**

Create a `.env` file in the root directory with the following variables:

DATABASE_URL=postgresql://openpg:your_strong_password@localhost:5432/your_database_name
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ODOO_URL=http://localhost:8069
ODOO_DB=your_database_name
ODOO_USERNAME=your_email    
ODOO_PASSWORD=your_password

5. **Run the Application:**
   ```bash
   uvicorn app.main:app --reload
   ```

6. **Access the API:**
   Open your browser and navigate to:
   ```
   http://127.0.0.1:8000/docs
   ```

## Running Tests

The project includes comprehensive tests for API endpoints with real Odoo integration and database operations.

### Install Test Dependencies

```bash
pip install pytest pytest-asyncio httpx
```

### Run All Tests

```bash
python -m tests.run_tests
```

### Run Individual Test Files

```bash
# Run real Odoo integration tests
python -m pytest tests/test_odoo_integration.py -v

# Run CRUD function tests
python -m pytest tests/test_crud_functions.py -v
```

The integration tests create actual tickets in your Odoo instance and verify that they are properly synchronized with your PostgreSQL database. After testing, all test data is cleaned up.

See the [tests/README.md](tests/README.md) file for more details about testing.

## API Endpoints

### Authentication
- `/token` - Login and get access token

### User Endpoints
- `/api/users/me` - Get current user information

### Ticket Endpoints
- `/api/tickets/` - Get all tickets for a user
- `/api/tickets/filter` - Filter tickets by status and priority
- `/api/tickets/count` - Get ticket counts by status
- `/api/tickets/statuses` - Get all possible ticket statuses
- `/api/tickets/{ticket_id}` - Get details for a specific ticket
- `/api/tickets/` (POST) - Create a new ticket
- `/api/tickets/{ticket_id}/messages` - Add a message to a ticket
- `/api/tickets/{ticket_id}` (PUT) - Update a ticket
- `/api/tickets/{ticket_id}` (DELETE) - Delete a ticket
