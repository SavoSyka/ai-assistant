from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, Column, String
from sqlmodel import Field, SQLModel


class LeadStatus(str, Enum):
    pending = "pending"
    contact_in_progress = "contact_in_progress"
    awaiting_confirmation = "awaiting_confirmation"
    confirmed = "confirmed"
    rejected = "rejected"
    scheduled = "scheduled"


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: Optional[str] = Field(default=None)
    status: LeadStatus = Field(default=LeadStatus.pending)
    telegram_user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True, index=True),
    )
    telegram_access_hash: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    telegram_username: Optional[str] = Field(
        default=None,
        sa_column=Column(String(64), nullable=True, index=True),
    )
    last_message_id: Optional[int] = None
    last_contacted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    notes: Optional[str] = None

    def mark_updated(self) -> None:
        self.updated_at = datetime.utcnow()
