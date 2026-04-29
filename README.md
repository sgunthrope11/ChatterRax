# ChatterRax

ChatterRax is a Flask-based support intake and ticket triage app. It includes a Microsoft 365 demo domain, a test domain for swap demos, PostgreSQL ticket storage, optional Gemini fallback, and email alerts when tickets are created.

The production project lives here:

```text
Triage_System/Live_hosting_Project
```

Start with the full project README:

[Live Hosting Project README](Triage_System/Live_hosting_Project/README.md)

Key files:

- `Triage_System/Live_hosting_Project/app.py` - app entry point
- `Triage_System/Live_hosting_Project/backend/app.py` - Flask routes
- `Triage_System/Live_hosting_Project/backend/bot_logic.py` - bot routing and ticket logic
- `Triage_System/Live_hosting_Project/triage_core/` - domain loading, detection, and memory
- `Triage_System/Live_hosting_Project/providers/` - knowledge, Gemini, and email providers
- `Triage_System/Live_hosting_Project/domains/` - plug-and-play domain packs

Do not commit real `.env` files. Use the tracked example files inside `Triage_System/Live_hosting_Project` when setting up a local or hosted deployment.
