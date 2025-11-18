from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./leads.db"

    telegram_api_id: int
    telegram_api_hash: str
    telegram_bot_token: str | None = None
    telegram_session_name: str = "ai_assistant"
    telegram_session_dir: str = "."

    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"
    calendly_link: str

    greeting_template: str = (
        "Привет, {name}! Это команда GordovCode. "
        "Вы оставляли заявку на сайте? Подтвердите, пожалуйста."
    )
    acceptance_template: str = (
        "Отлично! Вот ссылка на Calendly, чтобы выбрать удобное время созвона: {calendly_link}"
    )
    company_profile: str = (
        "Мы агентство заказной разработки GordovCode. "
        "Помогаем внедрять ИИ в бизнес-процессы и создаем мобильные приложения, сайты, CRM и любые цифровые продукты. "
        "Подробнее рассказываем на созвоне с техническими специалистами."
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
