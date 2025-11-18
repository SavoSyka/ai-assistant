# AI Lead Assistant

FastAPI + Pyrogram service that stores inbound lead requests, reaches out to prospects over Telegram, and sends a Calendly link once they confirm interest.

## Main components

1. **REST API (`main.py`)** – `POST /leads` accepts `name` plus a phone number, Telegram username, or both; the service normalizes the provided contact data and persists it via SQLModel before scheduling Telegram outreach.
2. **Tilda webhook** – `POST /leads/webhooks/tilda` lets Tilda send form submissions directly to the application; it extracts the name along with phone/username fields, sanitizes the contacts, and creates the same Lead record as the manual endpoint.
3. **Worker (`worker.py`)** – runs a Pyrogram client, pulls pending leads, imports contacts to capture `access_hash`, sends greeting messages, and classifies replies with OpenAI before sharing your Calendly link.
4. **Services** – isolated modules for DB access, Telegram logic, and natural-language classification.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env  # fill secrets
python -c "from app.db import init_db; init_db()"  # one-time DB creation
uvicorn main:app --reload
python worker.py
```

## Configuration

Set the following environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL, defaults to `sqlite:///./leads.db` |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Telegram application credentials |
| `TELEGRAM_SESSION_NAME` | Session file name for Pyrogram |
| `TELEGRAM_SESSION_DIR` | Directory where Pyrogram session files are stored (set to `/sessions` inside Docker) |
| `OPENAI_API_KEY` | Access token for GPT classification/generation |
| `OPENAI_MODEL` | (Optional) Model name, defaults to `gpt-4.1-mini` |
| `CALENDLY_LINK` | Link shared once interest confirmed |

### Docker usage

1. Copy `.env.example` to `.env` and, if you plan to use the bundled Postgres container, set  
   `DATABASE_URL=postgresql+psycopg://leads:leads@db:5432/leads` and `TELEGRAM_SESSION_DIR=/sessions`.
2. Create a local folder `mkdir -p sessions` so Pyrogram can persist its auth files.
3. Build and start everything: `docker compose up --build`.
4. API becomes available at `http://localhost:8000`, worker runs in the background, and Postgres data lives in the `db-data` volume.

### Swagger / docs

FastAPI automatically exposes Swagger UI at `http://localhost:8000/docs` (and ReDoc at `/redoc`) where you can test the `POST /leads` request interactively.

### Tilda webhook configuration

1. Configure the form on Tilda to send a `POST` request to `http://<your-host>/leads/webhooks/tilda`. Paste the URL into the webhook settings for the form or page.
2. Tilda submits each form field (name, phone, email, etc.) in the `data`, `fields`, and `post` payload keys. The application looks for keys that include `name`/`имя`/`fio` for the lead’s name, `phone`/`телефон`/`tel` for the phone number, and `username`/`логин`/`ник`/`telegram` for the Telegram handle.
3. The phone number is sanitized to keep only digits and an optional leading `+`. If the webhook arrives with noisy formatting (spaces, parentheses, hyphens), the service still normalizes it before saving.
4. On success the webhook responds with `201 Created` and the stored Lead payload, exactly as the `/leads` route does. If Tilda repeatedly retries (because it received anything other than 2xx), check the webhook log to see the validation error message returned by FastAPI.
5. When the webhook contains both phone and username, the worker will try the username first and fall back to the phone contact if the message cannot be delivered via username.

## Flow

1. Website sends lead to `/leads/webhooks/tilda` (or you can still post manually to `/leads`), providing the name plus either the phone number, the Telegram username, or both.
2. Worker sees a pending lead, resolves the username (or imports the phone contact as a fallback), saves `telegram_user_id`/`access_hash`, и через GPT генерирует персонализированное приветствие (упоминает заявку GordovCode и предлагает созвон).
3. Входящие ответы классифицируются (`accept`/`reject`/`question`/`ambiguous`):
   - при отказе модель формирует вежливое извинение,
   - на вопросы даётся ответ на основе описания GordoveCode,
   - при согласии автоматически отправляется Calendly.
4. Lead переходит в `scheduled` после отправки ссылки.
