from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .models import LeadStatus


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    telegram_username: str | None = Field(default=None, min_length=3, max_length=64)

    @model_validator(mode="after")
    def ensure_contact(cls, values: "LeadCreate") -> "LeadCreate":
        if not values.phone and not values.telegram_username:
            raise ValueError("Укажите номер телефона или Telegram username (или оба).")
        return values


class LeadRead(BaseModel):
    id: int
    name: str
    phone: str | None
    telegram_username: str | None
    status: LeadStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
