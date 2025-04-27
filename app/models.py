from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from pydantic import BaseModel, EmailStr
from app.database import Base
from datetime import datetime

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

# SQLAlchemy ORM Models
class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, index=True, nullable=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

    tickets = relationship("TicketORM", back_populates="owner")

class TicketORM(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    priority = Column(String, default="1")
    stage_id = Column(Integer, default=1)
    odoo_ticket_id = Column(Integer, index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    partner_email = Column(String, nullable=True)
    
    # Additional fields for ticket status
    status = Column(String, default="new")  # new, in_progress, waiting, solved, closed
    is_resolved = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Fields for diagnostic test booking context
    diagnostic_test_id = Column(Integer, nullable=True)
    lab_id = Column(Integer, nullable=True)
    booking_id = Column(Integer, nullable=True)

    # Relationships
    owner = relationship("UserORM", back_populates="tickets")
    messages = relationship("TicketMessageORM", back_populates="ticket", cascade="all, delete-orphan")

class TicketMessageORM(Base):
    __tablename__ = "ticket_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))
    message = Column(Text)
    odoo_message_id = Column(Integer, nullable=True)
    is_from_support = Column(Boolean, default=False)  # True if from support team, False if from user
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    ticket = relationship("TicketORM", back_populates="messages")
