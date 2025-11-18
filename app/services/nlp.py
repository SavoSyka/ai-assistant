import re
from enum import Enum

from openai import AsyncOpenAI

from ..config import get_settings

settings = get_settings()


class IntentLabel(str, Enum):
    accept = "accept"
    reject = "reject"
    question = "question"
    ambiguous = "ambiguous"


class LeadConversationAI:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._accept_patterns = [
            r"\bда\b",
            r"\bдавай(те)?\b",
            r"\bконечно\b",
            r"\bготов\b",
            r"\bсоглас(ен|на)\b",
            r"\bок\b",
            r"\bокей\b",
            r"\bпоехали\b",
            r"\bинтересно\b",
        ]
        self._reject_patterns = [
            r"\bнет\b",
            r"\bне интересно\b",
            r"\bнеинтересно\b",
            r"\bне надо\b",
            r"\bне нужен\b",
            r"\bне пишите\b",
            r"\bне беспокойте\b",
            r"\bошибка\b",
            r"\bне оставлял[аи]?\b",
            r"\bспам\b",
            r"\bне актуально\b",
        ]
        self._question_patterns = [
            r"\bчто\b",
            r"\bкак\b",
            r"\bкогда\b",
            r"\bкакие\b",
            r"\bкакая\b",
            r"\bсколько\b",
            r"\bможно\b",
            r"\bмогу\b",
            r"\bчем\b",
            r"\bгде\b",
        ]

    async def classify(self, message: str) -> IntentLabel:
        text = (message or "").strip()
        if not text:
            return IntentLabel.ambiguous
        normalized = text.lower()

        if self._match(normalized, self._accept_patterns):
            return IntentLabel.accept
        if self._match(normalized, self._reject_patterns):
            return IntentLabel.reject
        if "?" in text or self._match(normalized, self._question_patterns):
            return IntentLabel.question

        prompt = (
            "Ты работаешь в отделе продаж GordovCode. "
            "Оцени сообщение лида и верни один ярлык из списка:\n"
            "- accept: пользователь подтверждает, что оставлял заявку и готов обсудить созвон.\n"
            "- reject: пользователь отказывается, говорит что это ошибка или просит не писать.\n"
            "- question: пользователь задаёт вопрос, и нужно ответить по нашему описанию.\n"
            "- ambiguous: всё остальное.\n"
            "Ответь только одним словом (accept/reject/question/ambiguous).\n"
            f"Сообщение лида: ```{message}```"
        )

        completion = await self._client.responses.create(
            model=self._model,
            input=prompt,
            temperature=0.0,
        )
        raw = (completion.output_text or "").strip().lower()
        for label in IntentLabel:
            if label.value in raw:
                return label
        return IntentLabel.ambiguous

    async def generate_greeting(self, name: str) -> str:
        prompt = (
            "Напиши короткое приветственное сообщение для лида GordovCode.\n"
            "- укажи, что мы увидели его заявку на сайте GordovCode;\n"
            "- уточни, действительно ли он оставлял заявкку и удобно ли ему обсудить задачу на коротком созвоне;\n"
            "- не объясняй подробно чем занимается компания, максимум одно упоминание;\n"
            "- стиль: 1-2 предложения, без эмодзи, без вставки ссылки.\n"
            f"Имя лида: {name}.\n"
            "Выведи только текст сообщения."
        )
        return await self._single_text_response(prompt)

    async def generate_rejection_reply(self, name: str | None = None) -> str:
        prompt = (
            "Сформулируй ответ на отказ лида без приветствия и без обращения по имени. "
            "Нужно коротко извиниться за беспокойство, поблагодарить за ответ и сказать, что будем на связи, если ситуация изменится. "
            "Стиль дружелюбный, 1-2 предложения."
        )
        return await self._single_text_response(prompt)

    async def answer_question(self, message: str) -> str:
        prompt = (
            "Ответь на вопрос лида про GordovCode, используя информацию ниже.\n"
            f"{settings.company_profile}\n"
            "Ответ должен быть конкретным, 2-3 предложения, упомяни что можем показать больше на коротком созвоне.\n"
            "Сообщение лида: " + message
        )
        return await self._single_text_response(prompt)

    async def _single_text_response(self, prompt: str) -> str:
        completion = await self._client.responses.create(
            model=self._model,
            input=prompt,
            temperature=0.8,
        )
        return (completion.output_text or "").strip()

    @staticmethod
    def _match(text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)
