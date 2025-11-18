from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..db import get_session
from ..models import Lead
from ..schemas import LeadCreate, LeadRead

router = APIRouter(prefix="/leads", tags=["leads"])


class TildaField(BaseModel):
    name: str
    value: str


class TildaWebhookPayload(BaseModel):
    data: Sequence[TildaField] | None = None
    fields: Dict[str, str] | None = None
    post: Dict[str, Any] | None = None

    class Config:
        extra = "allow"


def _persist_lead(name: str, phone: str | None, telegram_username: str | None) -> LeadRead:
    with get_session() as session:
        lead = Lead(name=name, phone=phone, telegram_username=telegram_username)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return LeadRead.model_validate(lead)


def _normalize_phone(value: str) -> str | None:
    sanitized = value.strip()
    if not sanitized:
        return None

    if sanitized.startswith("00"):
        sanitized = f"+{sanitized[2:]}"

    digits = re.sub(r"[^\d+]", "", sanitized)
    if digits.count("+") > 1:
        digits = digits.replace("+", "")

    if digits.startswith("+"):
        digits = f"+{digits[1:].lstrip('+')}"
    return digits or None


def _normalize_username(value: str) -> str | None:
    normalized = value.strip().lstrip("@")
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return None
    if not re.match(r"^[A-Za-z0-9_]+$", normalized):
        return None
    return normalized


def _prepare_contact(
    phone: str | None,
    username: str | None,
) -> tuple[str | None, str | None]:
    normalized_phone = _normalize_phone(phone) if phone else None
    normalized_username = _normalize_username(username) if username else None
    if not normalized_phone and not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите номер телефона или Telegram username.",
        )
    return normalized_phone, normalized_username


def _extract_fields(payload: TildaWebhookPayload) -> Dict[str, str]:
    extracted: Dict[str, str] = {}

    def add_field(key: str, raw_value: Any) -> None:
        normalized_key = key.strip().lower()
        normalized_value = str(raw_value).strip()
        if normalized_value:
            extracted[normalized_key] = normalized_value

    if payload.data:
        for field in payload.data:
            add_field(field.name, field.value)

    if payload.fields:
        for field_name, field_value in payload.fields.items():
            add_field(field_name, field_value)

    if payload.post:
        for field_name, field_value in payload.post.items():
            add_field(field_name, field_value)

    return extracted


def _match_field(values: Dict[str, str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        for value_name, value in values.items():
            if candidate in value_name:
                return value
    return None


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(payload: LeadCreate) -> LeadRead:
    phone, username = _prepare_contact(payload.phone, payload.telegram_username)
    return _persist_lead(payload.name, phone, username)


@router.post(
    "/webhooks/tilda",
    response_model=LeadRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lead_from_tilda(payload: TildaWebhookPayload) -> LeadRead:
    values = _extract_fields(payload)

    name = _match_field(values, ("name", "fullname", "имя", "ф.и.о", "fio"))
    phone = _match_field(
        values,
        ("phone", "телефон", "tel", "mobile", "whatsapp"),
    )
    username = _match_field(
        values,
        ("username", "логин", "ник", "tg", "telegram", "telegram_username"),
    )

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось распознать имя заявки из данных Tilda.",
        )

    if not phone:
        phone = None

    phone, username = _prepare_contact(phone, username)
    return _persist_lead(name, phone, username)
