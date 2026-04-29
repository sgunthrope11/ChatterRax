# ChatterRax Live Hosting Project

ChatterRax is a Flask-based support intake and ticket triage app. It ships with a Microsoft 365 demo domain and a small test domain so teams can verify domain swapping before adding their own production domain packs.

The app collects a user's name, email, and department, runs the message through deterministic bot logic, searches local domain knowledge, optionally uses Gemini for ambiguous cases, creates PostgreSQL tickets when escalation is needed, and can email ticket alerts to one or more recipients.

## What Is Included

- Browser frontend: `templates/`, `static/js/`, and `static/css/`
- Flask backend: `backend/app.py`
- Bot routing and memory: `backend/bot_logic.py`, `triage_core/`
- Local knowledge retrieval: `providers/knowledge_provider.py`
- Gemini provider: `providers/gemini_provider.py`
- Ticket email provider: `providers/email_provider.py`
- PostgreSQL schema: `schema.sql`
- Domain packs: `domains/microsoft365/domain.json` and `domains/test/domain.json`
- Railway config: `railway.toml`, `Procfile`, `requirements.txt`

## Request Flow

1. The user enters name, email, and department.
2. The frontend sends chat messages to `POST /chat`.
3. Flask validates the payload and creates or reuses a chat user/session.
4. User and bot messages are saved in PostgreSQL.
5. `handle_message()` routes the issue using keywords, fuzzy matching, memory, local knowledge, and ticket rules.
6. Gemini is used only when local logic does not produce a clean answer.
7. If a ticket is created, the backend links it to the session and sends ticket email alerts if enabled.
8. The frontend ends the chat after ticket creation and shows a `Restart Chat` button for a fresh session.

## Main Routes

- `/chatbot` - support intake page
- `/chat` - chat API used by the frontend
- `/admin` - admin ticket console
- `/tickets` - open and in-progress ticket JSON
- `/ticket/update` - update ticket status
- `/health` - app/database health check
- `/health/gemini` - Gemini configuration status

## Database Schema

The schema is defined in `schema.sql` and runs on startup using idempotent `CREATE TABLE IF NOT EXISTS` statements.

Table links:

- `tickets.user_id` references `users.user_id`
- `chat_sessions.user_id` references `users.user_id`
- `chat_sessions.ticket_id` references `tickets.ticket_id`
- `chat_messages.session_id` references `chat_sessions.session_id`

## Environment Files

Do not commit real secrets. The project intentionally separates secret settings from safe domain settings.

Tracked examples:

- `.env.example` - general local/production placeholders
- `.env.domain.example` - safe domain-only placeholders
- `.env.railway.example` - Railway variable reference

Ignored local files:

- `.env` - local secrets and service credentials
- `.env.domain` - local domain switching
- `GEMINI_PROMPTS.md` - private demo prompts

## Local Environment Setup

Create `.env` for secrets:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE

GEMINI_ENABLED=True
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=30

FLASK_DEBUG=False
CHAT_STATE_TTL_SECONDS=21600

TICKET_EMAIL_ENABLED=False
TICKET_EMAIL_TO=admin1@gmail.com,admin2@gmail.com
TICKET_ADMIN_URL=http://127.0.0.1:5000/admin
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your_sending_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM=your_sending_gmail@gmail.com
```

Create `.env.domain` for safe domain switching:

```env
BOT_DOMAIN=microsoft365

# For multiple domains:
# BOT_DOMAINS=microsoft365,test
```

If `BOT_DOMAINS` is set, it takes priority over `BOT_DOMAIN`.

## Running Locally

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run the app:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000/chatbot
```

For local Railway Postgres testing, use Railway's public/external Postgres URL, not the internal `postgres.railway.internal` URL.

## Railway Deployment

Railway uses:

- `railway.toml`
- `Procfile`
- `requirements.txt`
- `gunicorn app:app`

Add variables in Railway's Variables tab. Railway does not automatically read `.env.railway.example`; use it as a copy/reference file.

Minimum Railway variables:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_ENABLED=True
BOT_DOMAIN=microsoft365
FLASK_DEBUG=False
```

Ticket email variables:

```env
TICKET_EMAIL_ENABLED=True
TICKET_EMAIL_TO=admin1@gmail.com,admin2@gmail.com
TICKET_ADMIN_URL=https://your-railway-app.up.railway.app/admin
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your_sending_gmail@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM=your_sending_gmail@gmail.com
```

Use a Gmail app password, not a normal Gmail password.

## Domain Packs

The Microsoft 365 pack is the default demo:

```env
BOT_DOMAIN=microsoft365
```

The test pack is included for domain swap demos:

```env
BOT_DOMAIN=test
```

Use both:

```env
BOT_DOMAINS=microsoft365,test
```

To replace the demo with your own domain, add:

```text
domains/your-domain/domain.json
```

Then set:

```env
BOT_DOMAIN=your-domain
```

A replacement domain should define:

- `name`
- `domain_label`
- `default_service`
- `supported_scope`
- `client`
- `services`
- `intents`
- `service_intent_responses`
- `knowledge_resources`
- optional `routing`
- optional `gemini.extra_rules`

See `domains/README.md` for the domain pack format.

## Gemini Behavior

Gemini is called from `providers/gemini_provider.py` only after local logic has tried routing, memory, known issues, knowledge resources, and deterministic fallback paths.

Gemini receives the user message plus compact support context. It does not receive the full user profile. Name, email, and department are used by the backend for sessions and tickets.

For live demos, Gemini-generated replies are marked with:

```text
-gemini
```

## Ticket Emails

Ticket email alerts are sent only after a ticket is successfully created.

Multiple recipients are supported with commas:

```env
TICKET_EMAIL_TO=admin1@gmail.com,admin2@gmail.com,manager@gmail.com
```

The email includes:

- ticket ID
- priority
- description
- user name/email/department
- service and intent
- admin console link from `TICKET_ADMIN_URL`

Each recipient receives a separate email.

## Production Notes

- Do not commit `.env`, `.env.domain`, or `GEMINI_PROMPTS.md`.
- Restart the app after changing domain env values.
- Keep M365 as the placeholder/demo pack unless replacing it intentionally.
- Use Railway's public database URL for local testing.
- If Gmail SMTP fails, verify the app password, 2-Step Verification, and recipient list.
