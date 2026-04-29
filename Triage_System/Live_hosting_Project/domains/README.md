# Domain Packs

ChatterRax currently ships with two domain packs:

- `domains/microsoft365/domain.json`
- `domains/test/domain.json`

The Microsoft 365 pack keeps the live demo focused on Microsoft 365. If no domain environment variable is set, ChatterRax automatically loads `microsoft365`. The test pack is included so you can demo replacement and multi-domain behavior without editing the M365 pack.

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

To replace Microsoft 365 with the test pack:

```powershell
$env:BOT_DOMAIN = "test"
python app.py
```

To point directly at a JSON file:

```powershell
$env:BOT_DOMAIN_PATH = "C:\path\to\domain.json"
python app.py
```

To load Microsoft 365 and the test pack together:

```powershell
$env:BOT_DOMAINS = "microsoft365,test"
python app.py
```

In hosted production, set the same values through your hosting provider's environment/secret settings instead of PowerShell.

For the current demo, you can leave `BOT_DOMAIN`, `BOT_DOMAINS`, and `BOT_DOMAIN_PATH` unset.

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
- `routing`: optional routing hints such as loose service terms, service conflict rules, and fuzzy-match exclusions.

The Microsoft 365 pack intentionally does not replace the built-in replies. It acts as the default domain identity while the current Microsoft demo behavior stays active.

For a single non-built-in replacement domain, the app defaults the `replace_builtin_*` flags to `true` if you leave them unset. That keeps a new domain clean by default. Use `BOT_DOMAINS=microsoft365,another_domain` only when you intentionally want an overlay demo that combines packs.

## Where Knowledge Lives

There are two knowledge sources:

1. Built-in Python knowledge resources in `providers/knowledge_provider.py` and the expanded resource files under `providers/`.
2. Optional JSON knowledge resources inside a domain pack under `knowledge_resources`.

For the current Microsoft 365 demo, the built-in Microsoft playbook remains available only because the Microsoft pack declares `built_in_profile: "microsoft365"`. Replacement domains do not receive that built-in Microsoft knowledge unless they are deliberately loaded alongside the Microsoft pack.

If a future pack defines `knowledge_resources`, `providers/knowledge_provider.py` normalizes those entries and adds them to retrieval. Runtime learned knowledge is off unless the pack sets `include_learned_knowledge: true`.

## Is The JSON Needed After Startup?

Yes, the JSON file must exist when the app process starts.

The app reads the domain pack at Python import/startup time. After that, the loaded data is stored in module-level variables inside `bot_logic`, `knowledge_provider`, and `gemini_provider`.

That means:

- If the JSON file is deleted after startup, the already-running process keeps using the copy it loaded into memory.
- If the app restarts and the JSON file is missing, the pack cannot load.
- If the JSON file is changed while the app is already running, the current process does not automatically reload it.

To apply JSON changes, restart or redeploy the app. Most hosting providers restart the app when you push new code or trigger a redeploy.

## Domain Pack Fields

A domain pack can define:

- `name`: folder-style domain name, such as `microsoft365`.
- `domain_label`: display label for the active domain.
- `default_service`: fallback service when no specific service is detected.
- `supported_scope`: text used when the bot explains what it supports.
- `built_in_profile`: optional internal profile name. Leave this out for replacement domains.
- `include_learned_knowledge`: whether to load runtime learned knowledge from `LEARNED_KNOWLEDGE_PATH`.
- `client`: browser-facing text such as subtitle, input placeholder, welcome message, and quick-action prompt template.
- `routing`: optional domain-owned routing hints.
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

For a single replacement domain, omitted replacement flags default to `true`. For the current Microsoft 365 demo, they are explicitly false so the live demo keeps the Microsoft built-in behavior.

## Replacement Domain Example

Create:

```text
domains/crm/domain.json
```

Minimal replacement pack:

```json
{
  "name": "crm",
  "domain_label": "CRM",
  "default_service": "crm portal",
  "supported_scope": "CRM account, billing, and inventory support.",
  "client": {
    "chat_subtitle": "CRM support triage.",
    "input_placeholder": "Describe your CRM issue...",
    "welcome_template": "Hi{name_part} I am ChatterRax, a CRM bot here to help you out.",
    "quick_action_template": "Work on {label}."
  },
  "services": {
    "billing portal": {
      "label": "Billing Portal",
      "keywords": ["billing", "invoice", "payment"],
      "follow_up": "Tell me which billing action failed.",
      "reply_opener": "For Billing Portal, start with the invoice or payment action.",
      "capability_terms": ["invoice", "payment"]
    }
  },
  "intents": {
    "sign_in": {
      "keywords": ["login", "sign in", "password"],
      "wrap_up": "If sign-in still fails, keep the exact error message."
    }
  },
  "service_intent_responses": {
    "billing portal|sign_in": [
      "Billing Portal sign-in needs the account and browser path checked first.",
      "Try a private browser window and confirm the account shown on the sign-in page."
    ]
  },
  "knowledge_resources": [
    {
      "id": "crm_billing_login",
      "service": "billing portal",
      "intent": "sign_in",
      "title": "Billing portal login fails",
      "keywords": ["billing", "login", "sign in"],
      "steps": [
        "Open the billing portal in a private browser window.",
        "Confirm the account email shown on the login page."
      ]
    }
  ],
  "gemini": {
    "extra_rules": [
      "Stay inside CRM support. Do not route to services outside this pack."
    ]
  }
}
```

Then set:

```text
BOT_DOMAIN=crm
```

Because this is not a built-in profile, the Microsoft demo data is replaced by default.

## `.env` Examples

The local `.env` file belongs at the project root:

```text
Live_hosting_Project/.env
```

For example:

```text
C:\path\to\Live_hosting_Project\.env
```

`backend/app.py` loads this file before importing the bot and providers:

```text
Live_hosting_Project/backend/app.py
```

`providers/gemini_provider.py` also loads the same root `.env` file directly:

```text
Live_hosting_Project/providers/gemini_provider.py
```

`triage_core/domain_config.py` does not load `.env` by itself. It reads from `os.environ`, so the variables must already be loaded before `bot_logic`, `knowledge_provider`, or `gemini_provider` import it. In normal app startup, `backend/app.py` handles that.

### Current Microsoft 365 Demo `.env`

This is enough for the current M365 demo if your environment supplies `DATABASE_URL`:

```text
# Local development only. In production, set these in the hosting dashboard.
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

Multiple packs:

```text
BOT_DOMAINS=microsoft365,test
```

### Gemini `.env`

`providers/gemini_provider.py` expects these values from the root `.env` or the hosting environment:

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

`CHAT_STATE_TTL_SECONDS` controls how long in-memory chat state is kept before old browser/session state is pruned. The default is 21600 seconds, or 6 hours.

### Hosted Production Variables

Do not upload real `.env` files. Add the same values through your hosting provider's environment/secret settings. A typical M365 demo setup looks like:

```text
DATABASE_URL=postgresql://...
GEMINI_ENABLED=True
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
BOT_DOMAIN=microsoft365
FLASK_DEBUG=False
```

Use `.env.example` or `.env.production.example` as clean import templates. They only list variables this app currently reads.

Remove any older support-link or recommended-article URL variables from your hosting provider if they are still present. The app no longer reads or needs those values.
