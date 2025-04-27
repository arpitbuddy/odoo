from pydantic import BaseModel, EmailStr
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class UserBase(BaseModel):
    username: str
    email: EmailStr | None = None
    full_name: str | None = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class UserInDB(User):
    hashed_password: str

class TicketBase(BaseModel):
    name: str
    description: str
    priority: str = "1"
    user_id: int

class TicketCreate(TicketBase):
    # Optional fields for diagnostic tests context
    diagnostic_test_id: int | None = None
    lab_id: int | None = None
    booking_id: int | None = None

class Ticket(TicketBase):
    id: int
    stage_id: int
    status: str | None = None
    is_resolved: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    odoo_ticket_id: int | None = None

    class Config:
        from_attributes = True

class TicketMessageBase(BaseModel):
    message: str
    ticket_id: int

class TicketMessageCreate(BaseModel):
    message: str

class TicketMessage(TicketMessageBase):
    id: int
    is_from_support: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TicketDetail(Ticket):
    messages: list[TicketMessage] = []

    class Config:
        from_attributes = True

class TicketStatusCount(BaseModel):
    new: int
    in_progress: int
    solved: int
    closed: int
    total: int

class TicketStatus(BaseModel):
    id: str
    name: str

class TicketStatuses(BaseModel):
    statuses: list[TicketStatus]
