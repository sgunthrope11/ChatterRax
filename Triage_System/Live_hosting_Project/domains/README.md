# Domain Packs

ChatterRax currently ships with one domain pack:

- `domains/microsoft365/domain.json`

That pack keeps the live demo focused on Microsoft 365. If no domain environment
variable is set, ChatterRax automatically loads `microsoft365`.

## Environment Setup

For the current Microsoft 365 demo, no domain env var is required:

```powershell
python app.py
```

To explicitly select the Microsoft 365 pack:

```powershell
$env:BOT_DOMAIN = "microsoft365"
python app.py
```

To point directly at a JSON file:

```powershell
$env:BOT_DOMAIN_PATH = "C:\path\to\domain.json"
python app.py
```

To load multiple packs later, if more are added:

```powershell
$env:BOT_DOMAINS = "microsoft365,another_domain"
python app.py
```

On Railway, set these in the Variables tab instead of using PowerShell:

```text
BOT_DOMAIN=microsoft365
```

For the current demo, you can leave `BOT_DOMAIN`, `BOT_DOMAINS`, and
`BOT_DOMAIN_PATH` unset.

## Load Flow

The JSON file is read by `triage_core/domain_config.py`.

That module exposes:

- `load_domain_packs()`: loads the active domain pack or packs.
- `service_names(pack)`: returns the valid service names.
- `intent_names(pack)`: returns the valid intent names.
- `domain_knowledge_resources(pack)`: normalizes JSON knowledge entries into the structure used by retrieval.

Then the loaded pack is used in three places:

- `backend/bot_logic.py` calls `load_domain_packs()` and applies the pack to routing.
- `providers/knowledge_provider.py` calls `load_domain_packs()` and loads the pack's knowledge resources.
- `providers/gemini_provider.py` calls `load_domain_packs()` and limits Gemini to the active domain's services and intents.

## What Bot Logic Applies

`backend/bot_logic.py` uses the pack to update:

- `SERVICE_KEYWORDS`: which words route to which app or service.
- `SERVICE_LABELS`: display names such as `Microsoft 365`.
- `SERVICE_FOLLOW_UPS`: what the bot asks when it needs more detail.
- `SERVICE_REPLY_OPENERS`: generic app-specific opening replies.
- `SERVICE_CAPABILITY_TERMS`: terms used for memory/context routing.
- `INTENT_KEYWORDS`: words that map to intents like `sync`, `sign_in`, or `update`.
- `SHORT_STEP_RESPONSES`: short deterministic troubleshooting steps.
- `SERVICE_INTENT_RESPONSES`: exact replies for a service plus intent pair.

The Microsoft 365 pack intentionally does not replace the built-in replies. It
acts as the default domain identity while the current Microsoft demo behavior
stays active.

## Where Knowledge Lives

There are two knowledge sources:

1. Built-in Python knowledge resources in `providers/knowledge_provider.py` and
   the expanded resource files under `providers/`.
2. Optional JSON knowledge resources inside a domain pack under
   `knowledge_resources`.

For the current Microsoft 365 demo, most content lives in the Python knowledge
resource files. The JSON pack is the plug-in point for future replacement or
overlay content.

If a future pack defines `knowledge_resources`, `providers/knowledge_provider.py`
normalizes those entries and adds them to retrieval. If the pack sets
`replace_builtin_knowledge: true`, only the pack's knowledge is used unless
`include_learned_knowledge` is also enabled.

## Is The JSON Needed After Startup?

Yes, the JSON file must exist when the app process starts.

The app reads the domain pack at Python import/startup time. After that, the
loaded data is stored in module-level variables inside `bot_logic`,
`knowledge_provider`, and `gemini_provider`.

That means:

- If the JSON file is deleted after startup, the already-running process keeps
  using the copy it loaded into memory.
- If the app restarts and the JSON file is missing, the pack cannot load.
- If the JSON file is changed while the app is already running, the current
  process does not automatically reload it.

To apply JSON changes, restart or redeploy the app.

On Railway, pushing a change or redeploying restarts the process, so updated
domain JSON is loaded on the next boot.

## Domain Pack Fields

A domain pack can define:

- `name`: folder-style domain name, such as `microsoft365`.
- `domain_label`: display label for the active domain.
- `default_service`: fallback service when no specific service is detected.
- `supported_scope`: text used when the bot explains what it supports.
- `client`: browser-facing text such as subtitle, input placeholder, welcome message, and quick-action prompt template.
- `services`: service labels, keyword lists, follow-up prompts, reply openers, and capability terms.
- `intents`: intent keyword lists and short deterministic troubleshooting steps.
- `service_intent_responses`: exact service+intent replies keyed as `"service|intent"`.
- `knowledge_resources`: local support playbook entries used by keyword retrieval.
- `gemini.extra_rules`: extra prompt rules for model fallback.

Replacement flags:

- `replace_builtin_services`
- `replace_builtin_intents`
- `replace_builtin_knowledge`
- `replace_builtin_responses`

These are useful for future non-Microsoft domains. For the current Microsoft 365
demo, leave them false or unset.

## `.env` Examples

The local `.env` file belongs at the project root:

```text
Live_hosting_Project/.env
```

In this project, that means:

```text
C:\Users\teric\Downloads\Ticketing System\Triage_System\Live_hosting_Project\.env
```

`backend/app.py` loads this file before importing the bot and providers:

```text
Live_hosting_Project/backend/app.py
```

`providers/gemini_provider.py` also loads the same root `.env` file directly:

```text
Live_hosting_Project/providers/gemini_provider.py
```

`triage_core/domain_config.py` does not load `.env` by itself. It reads from
`os.environ`, so the variables must already be loaded before `bot_logic`,
`knowledge_provider`, or `gemini_provider` import it. In normal app startup,
`backend/app.py` handles that.

### Current Microsoft 365 Demo `.env`

This is enough for the current M365 demo if Railway supplies `DATABASE_URL`:

```text
# Local development only. In Railway/production, set these in the hosting dashboard.
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE

GEMINI_ENABLED=True
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE

# Leave unset to use microsoft365 automatically.
# BOT_DOMAIN=microsoft365
```

For a deterministic local demo without Gemini:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
GEMINI_ENABLED=False
```

### Domain Pack `.env`

Use one of these approaches, not all three at the same time.

Default M365 behavior:

```text
# No domain variable required.
```

Explicit M365 domain:

```text
BOT_DOMAIN=microsoft365
```

Direct JSON path:

```text
BOT_DOMAIN_PATH=C:\path\to\domain.json
```

Multiple packs, if more are added later:

```text
BOT_DOMAINS=microsoft365,another_domain
```

### Gemini `.env`

`providers/gemini_provider.py` expects these values from the root `.env` or the
hosting environment:

```text
GEMINI_ENABLED=True
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT_SECONDS=30
GEMINI_TEMPERATURE=0.3
GEMINI_MAX_TOKENS=1024
GEMINI_THINKING_BUDGET=0
GEMINI_BYPASS_PROXY=True
GEMINI_TPM_LIMIT=250000
GEMINI_RPM_LIMIT=5
GEMINI_MIN_REQUEST_INTERVAL_SECONDS=0.25
GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS=3
GEMINI_RATE_LIMIT_RETRIES=1
GEMINI_429_COOLDOWN_SECONDS=8
GEMINI_429_MAX_COOLDOWN_SECONDS=300
```

### Database And App `.env`

`backend/db/connection.py` reads `DATABASE_URL` from the environment:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

`backend/app.py` also supports:

```text
FLASK_DEBUG=False
CHAT_STATE_TTL_SECONDS=21600
```

`CHAT_STATE_TTL_SECONDS` controls how long in-memory chat state is kept before
old browser/session state is pruned. The default is 21600 seconds, or 6 hours.

### Learned Knowledge `.env`

`providers/knowledge_provider.py` can optionally read learned knowledge from a
custom JSON file:

```text
LEARNED_KNOWLEDGE_PATH=C:\path\to\learned_knowledge.json
```

If unset, it defaults to:

```text
Live_hosting_Project/data/learned_knowledge.json
```

For the current Microsoft 365 demo, this can usually stay unset.

### Railway Variables

On Railway, do not upload `.env`. Add the same values in the Railway Variables
tab. A typical M365 demo setup looks like:

```text
DATABASE_URL=postgresql://...
GEMINI_ENABLED=True
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_MAX_TOKENS=1024
GEMINI_THINKING_BUDGET=0
```

Leave `BOT_DOMAIN`, `BOT_DOMAINS`, and `BOT_DOMAIN_PATH` unset unless you want
to override the default Microsoft 365 pack.
