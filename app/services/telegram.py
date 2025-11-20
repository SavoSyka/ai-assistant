import asyncio
import logging
from typing import Iterable

from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.handlers import MessageHandler
from pyrogram.raw.types import InputPhoneContact
from pyrogram.types import Message, User
from sqlmodel import select

from ..config import get_settings
from ..db import get_session
from ..models import Lead, LeadStatus
from .nlp import IntentLabel, LeadConversationAI

logger = logging.getLogger(__name__)
settings = get_settings()


class TelegramLeadService:
    def __init__(self) -> None:
        self._client = Client(
            settings.telegram_session_name,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            bot_token=settings.telegram_bot_token,
            workdir=settings.telegram_session_dir,
        )
        self._conversation_ai = LeadConversationAI()
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._client.start()
        self._client.add_handler(MessageHandler(self._handle_incoming_message, filters.private))
        self._started = True
        logger.info("Telegram client started")

    async def stop(self) -> None:
        if not self._started:
            return
        await self._client.stop()
        self._started = False

    async def process_pending(self, limit: int = 10) -> None:
        async with self._lock:
            leads = self._fetch_leads_by_status([LeadStatus.pending], limit)
            for lead in leads:
                await self._touch_lead(lead)

    async def _touch_lead(self, lead: Lead) -> None:
        try:
            greeting = await self._conversation_ai.generate_greeting(lead.name)
        except Exception:
            logger.exception("Failed to generate greeting via GPT for lead %s, using fallback", lead.id)
            greeting = settings.greeting_template.format(name=lead.name)

        user, used_phone = await self._resolve_user_for_lead(lead)
        if not user:
            logger.warning("Telegram user not found for lead %s", lead.id)
            self._update_lead_status(lead.id, LeadStatus.rejected, note="User not found in Telegram")
            return

        delivered_user = await self._deliver_greeting(lead, user, greeting, used_phone)
        if not delivered_user:
            return

        with get_session() as session:
            db_lead = session.get(Lead, lead.id)
            if not db_lead:
                return
            db_lead.telegram_user_id = delivered_user.id
            db_lead.telegram_access_hash = getattr(delivered_user, "access_hash", None)
            db_lead.status = LeadStatus.awaiting_confirmation
            db_lead.mark_updated()
            session.add(db_lead)
            session.commit()

    def _fetch_leads_by_status(self, statuses: Iterable[LeadStatus], limit: int) -> list[Lead]:
        with get_session() as session:
            statement = (
                select(Lead)
                .where(Lead.status.in_(tuple(statuses)))
                .order_by(Lead.created_at)
                .limit(limit)
            )
            return list(session.exec(statement).all())

    def _update_lead_status(self, lead_id: int | None, status: LeadStatus, note: str | None = None) -> None:
        if not lead_id:
            return
        with get_session() as session:
            lead = session.get(Lead, lead_id)
            if not lead:
                return
            lead.status = status
            lead.notes = note
            lead.mark_updated()
            session.add(lead)
            session.commit()

    async def _get_user_by_username(self, username: str) -> User | None:
        normalized = username.strip().lstrip("@")
        if not normalized:
            return None
        try:
            return await self._client.get_users(normalized)
        except RPCError as exc:
            logger.warning("Failed to resolve username %s: %s", username, exc)
            return None

    async def _import_user_by_phone(self, lead: Lead) -> User | None:
        if not lead.phone:
            return None
        try:
            result = await self._client.import_contacts(
                [InputPhoneContact(client_id=lead.id or 0, phone=lead.phone, first_name=lead.name, last_name="")]
            )
            return result.users[0] if result.users else None
        except RPCError as exc:
            logger.warning("Failed to import contact for lead %s: %s", lead.id, exc)
            return None

    async def _resolve_user_for_lead(self, lead: Lead) -> tuple[User | None, bool]:
        # Сначала пробуем найти по телефону (импорт контакта),
        # если не удалось — пробуем по username.
        if lead.phone:
            user = await self._import_user_by_phone(lead)
            if user:
                return user, True  # True = использовали телефон
        if lead.telegram_username:
            user = await self._get_user_by_username(lead.telegram_username)
            if user:
                return user, False
        return None, False

    async def _deliver_greeting(
        self,
        lead: Lead,
        user: User,
        greeting: str,
        used_phone: bool,
    ) -> User | None:
        try:
            await self._client.send_message(user.id, greeting)
            return user
        except RPCError as exc:
            logger.warning("Failed to send greeting to lead %s: %s", lead.id, exc)
            # Если изначально писали по телефону, пробуем запасным вариантом username.
            if used_phone and lead.telegram_username:
                fallback_user = await self._get_user_by_username(lead.telegram_username)
                if fallback_user:
                    try:
                        await self._client.send_message(fallback_user.id, greeting)
                        return fallback_user
                    except RPCError as fallback_exc:
                        logger.exception("Fallback send to lead %s via username failed: %s", lead.id, fallback_exc)
            self._update_lead_status(lead.id, LeadStatus.rejected, note=str(exc))
            return None

    async def _handle_incoming_message(self, client: Client, message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        with get_session() as session:
            lead = session.exec(select(Lead).where(Lead.telegram_user_id == user_id)).first()
            if not lead:
                return
            incoming_text = message.text or ""
            label = await self._conversation_ai.classify(incoming_text)
            if label == IntentLabel.accept:
                await client.send_message(
                    user_id,
                    settings.acceptance_template.format(calendly_link=settings.calendly_link),
                )
                lead.status = LeadStatus.scheduled
            elif label == IntentLabel.reject:
                try:
                    reply = await self._conversation_ai.generate_rejection_reply(lead.name)
                except Exception:
                    logger.exception("Failed to craft rejection reply for lead %s", lead.id)
                    reply = "Понял, спасибо за ответ! Если ситуация изменится, мы всегда на связи."
                await client.send_message(user_id, reply)
                lead.status = LeadStatus.rejected
            elif label == IntentLabel.question:
                try:
                    answer = await self._conversation_ai.answer_question(incoming_text)
                except Exception:
                    logger.exception("Failed to answer question for lead %s", lead.id)
                    answer = (
                        f"{settings.company_profile} Готовы обсудить подробнее на коротком созвоне "
                        "и показать, как можем помочь в вашей задаче."
                    )
                await client.send_message(user_id, answer)
                lead.status = LeadStatus.awaiting_confirmation
            else:
                lead.status = LeadStatus.awaiting_confirmation
            lead.last_message_id = message.id
            lead.mark_updated()
            session.add(lead)
            session.commit()
