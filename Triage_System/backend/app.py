import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

# Load environment variables before importing providers that read config at import time.
_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
load_dotenv(_ROOT_DIR / ".env")

from backend.bot_logic import handle_message
from backend.db.db_service import (
    create_chat_session,
    create_ticket_for_session,
    get_chat_messages,
    get_latest_session_summary,
    get_or_create_chat_user,
    get_open_tickets,
    save_chat_message,
    save_session_summary,
    update_ticket_status,
)
from providers.qwen_provider import warm_qwen_model
from providers.status_provider import check_microsoft_public_status

app = Flask(
    __name__,
    template_folder=str(_ROOT_DIR / "templates"),
    static_folder=str(_ROOT_DIR / "static"),
)
PENDING_TICKET_REQUESTS = {}
CONVERSATION_HISTORY = {}
ACTIVE_SESSIONS = {}        # keyed by conversation key; reused within one browser tab/session
MAX_HISTORY_TURNS = 6
SQL_HISTORY_TURNS = 24
_STATE_LOCK = threading.Lock()
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MODEL_KEEP_WARM_ENABLED = os.environ.get("MODEL_KEEP_WARM_ENABLED", "True").lower() == "true"
MODEL_KEEP_WARM_INTERVAL_SECONDS = int(
    os.environ.get("MODEL_KEEP_WARM_INTERVAL_SECONDS", "480")
)
MODEL_KEEP_WARM_IDLE_SECONDS = int(
    os.environ.get("MODEL_KEEP_WARM_IDLE_SECONDS", "900")
)
_MODEL_ACTIVITY = {
    "last_activity_at": 0.0,
    "thread": None,
}
PURE_TICKET_REQUESTS = {
    "ticket",
    "a ticket",
    "need a ticket",
    "need ticket",
    "open ticket",
    "create ticket",
    "make ticket",
    "start ticket",
    "support ticket",
    "human",
    "agent",
}


def _conversation_key(user_email, client_session_id=None):
    if client_session_id:
        return f"{user_email}::{client_session_id}"
    return user_email


def _is_valid_email(email):
    return bool(EMAIL_PATTERN.fullmatch(str(email or "").strip()))


def _looks_like_pure_ticket_request(message_text):
    normalized = str(message_text or "").strip().lower()
    return normalized in PURE_TICKET_REQUESTS


def _derive_ticket_issue_snapshot(summary_text, fallback_service=""):
    raw_summary = str(summary_text or "").strip()
    if not raw_summary:
        fallback = str(fallback_service or "").strip()
        return f"{fallback} issue" if fallback and fallback != "microsoft 365" else ""

    try:
        parsed = json.loads(raw_summary)
    except json.JSONDecodeError:
        fallback = str(fallback_service or "").strip()
        return f"{fallback} issue" if fallback and fallback != "microsoft 365" else ""

    current_focus = str(parsed.get("current_focus") or fallback_service or "").strip()
    threads = parsed.get("threads") or []
    for thread in threads:
        if str(thread.get("service") or "").strip() == current_focus:
            snippet = str(thread.get("snippet") or "").strip()
            if snippet:
                return snippet

    fallback = current_focus if current_focus and current_focus != "microsoft 365" else str(fallback_service or "").strip()
    return f"{fallback} issue" if fallback and fallback != "microsoft 365" else ""


def _append_conversation_turn(conversation_key, sender, message_text):
    with _STATE_LOCK:
        history = CONVERSATION_HISTORY.setdefault(conversation_key, [])
        history.append({
            "sender": sender,
            "message": str(message_text or "").strip(),
        })
        CONVERSATION_HISTORY[conversation_key] = history[-MAX_HISTORY_TURNS:]


def _sql_conversation_history(session_id, current_user_message=None):
    history = get_chat_messages(session_id, limit=SQL_HISTORY_TURNS + 1) or []
    if (
        current_user_message
        and history
        and history[-1].get("sender") == "user"
        and history[-1].get("message", "").strip() == str(current_user_message).strip()
    ):
        history = history[:-1]
    return history[-SQL_HISTORY_TURNS:]


def _model_keep_warm_loop():
    warm_qwen_model(reason="first-activity")

    while True:
        time.sleep(max(5, MODEL_KEEP_WARM_INTERVAL_SECONDS))
        with _STATE_LOCK:
            idle_for = time.time() - _MODEL_ACTIVITY["last_activity_at"]
        if idle_for >= MODEL_KEEP_WARM_IDLE_SECONDS:
            break
        warm_qwen_model(reason="keep-alive")

    with _STATE_LOCK:
        _MODEL_ACTIVITY["thread"] = None


def _start_model_keep_warm_if_needed():
    if not MODEL_KEEP_WARM_ENABLED:
        return

    with _STATE_LOCK:
        worker = _MODEL_ACTIVITY.get("thread")
        if worker and worker.is_alive():
            return

        worker = threading.Thread(
            target=_model_keep_warm_loop,
            name="model-keep-warm",
            daemon=True,
        )
        _MODEL_ACTIVITY["thread"] = worker

    worker.start()


def _record_model_activity():
    if not MODEL_KEEP_WARM_ENABLED:
        return

    with _STATE_LOCK:
        _MODEL_ACTIVITY["last_activity_at"] = time.time()

    _start_model_keep_warm_if_needed()


# =========================
# Navigation routes
# =========================
@app.route("/")
def home():
    return redirect(url_for("chatbot_page"))


@app.route("/chatbot")
def chatbot_page():
    _record_model_activity()
    return render_template("index.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/status", methods=["GET"])
def status():
    try:
        service_name = str(request.args.get("service", "")).strip() or None
        status_result = check_microsoft_public_status(service_name=service_name)
        return jsonify(status_result)
    except Exception as exc:
        print(f"Unexpected error in /status route: {exc}")
        return jsonify({
            "issue_found": False,
            "summary": "Unable to retrieve Microsoft public status right now.",
            "service": request.args.get("service") or "microsoft 365",
            "status_available": False,
            "stale": False,
            "error": True,
        }), 500


# =========================
# Chat route
# main endpoint that
# processes messages
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    try:
        _record_model_activity()
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "reply": "Invalid request. Please send a valid message.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        user_message = data.get("message", "").strip()
        user_data = data.get("user") or {}
        user_name = str(user_data.get("name", "")).strip()
        user_email = str(user_data.get("email", "")).strip().lower()
        user_department = str(user_data.get("department", "")).strip()
        client_session_id = str(data.get("client_session_id", "")).strip()

        if not user_message:
            return jsonify({
                "reply": "Please type a message before sending.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        if not user_name or not user_email or not user_department:
            return jsonify({
                "reply": "Please provide your name, work email, and department or team before starting the chat.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        if not _is_valid_email(user_email):
            return jsonify({
                "reply": "Please enter a valid work email address before sending your message.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        conversation_key = _conversation_key(user_email, client_session_id)

        user_id = get_or_create_chat_user(user_name, user_email, user_department)
        if user_id is None:
            return jsonify({
                "reply": "We are experiencing technical difficulties. Please try again shortly.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 500

        if not isinstance(user_id, int) or user_id <= 0:
            return jsonify({
                "reply": "Invalid user. Please refresh and try again.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        with _STATE_LOCK:
            session_id = ACTIVE_SESSIONS.get(conversation_key)
        if not session_id:
            session_id = create_chat_session(user_id, ticket_id=None)
            if session_id is None:
                return jsonify({
                    "reply": "We are experiencing technical difficulties. Please try again shortly.",
                    "resolved": False,
                    "ticket_id": None,
                    "error": True
                }), 500
            with _STATE_LOCK:
                ACTIVE_SESSIONS[conversation_key] = session_id

        user_message_saved = save_chat_message(session_id, "user", user_message)
        if not user_message_saved:
            print(f"Warning: Failed to save user message for session {session_id}")

        with _STATE_LOCK:
            pending_ticket_request = PENDING_TICKET_REQUESTS.get(conversation_key)
            cached_history = CONVERSATION_HISTORY.get(conversation_key, [])[-MAX_HISTORY_TURNS:]
        conversation_history = _sql_conversation_history(
            session_id,
            current_user_message=user_message,
        ) or cached_history
        session_summary = get_latest_session_summary(session_id)
        result = handle_message(
            user_message,
            awaiting_ticket_detail=bool(pending_ticket_request),
            conversation_history=conversation_history,
            session_summary=session_summary,
        )

        bot_message_saved = save_chat_message(session_id, "bot", result["reply"])
        if not bot_message_saved:
            print(f"Warning: Failed to save bot reply for session {session_id}")
        if result.get("thread_summary"):
            summary_saved = save_session_summary(session_id, result["thread_summary"])
            if not summary_saved:
                print(f"Warning: Failed to save thread summary for session {session_id}")

        _append_conversation_turn(conversation_key, "user", user_message)
        _append_conversation_turn(conversation_key, "bot", result["reply"])

        ticket_id = None
        if result.get("needs_ticket") and result.get("needs_description"):
            if pending_ticket_request:
                pending_ticket_request["latest_prompt"] = result["reply"]
            else:
                initial_issue_message = user_message
                if _looks_like_pure_ticket_request(user_message):
                    initial_issue_message = _derive_ticket_issue_snapshot(
                        result.get("thread_summary") or session_summary,
                        fallback_service=result.get("service"),
                    ) or user_message
                with _STATE_LOCK:
                    PENDING_TICKET_REQUESTS[conversation_key] = {
                        "initial_message": initial_issue_message,
                        "service": result.get("service"),
                    }
        elif not result.get("create_ticket"):
            with _STATE_LOCK:
                PENDING_TICKET_REQUESTS.pop(conversation_key, None)

        if result.get("create_ticket"):
            ticket_description = user_message
            priority = result.get("priority", "medium").lower()

            if pending_ticket_request:
                ticket_description = (
                    f"Initial request: {pending_ticket_request['initial_message']}\n"
                    f"Additional detail: {user_message}"
                )

            ticket_id = create_ticket_for_session(
                session_id=session_id,
                user_id=user_id,
                description=ticket_description,
                priority=priority
            )
            if ticket_id is None:
                return jsonify({
                    "reply": "We are experiencing technical difficulties. Please try again shortly.",
                    "resolved": False,
                    "ticket_id": None,
                    "error": True
                }), 500

            print(f"Ticket created: #{ticket_id}")
            with _STATE_LOCK:
                PENDING_TICKET_REQUESTS.pop(conversation_key, None)
                CONVERSATION_HISTORY.pop(conversation_key, None)
                ACTIVE_SESSIONS.pop(conversation_key, None)

        return jsonify({
            "reply": result["reply"],
            "resolved": result["resolved"],
            "ticket_id": ticket_id,
            "service": result.get("service"),
            "intent": result.get("intent"),
            "priority": result.get("priority", "medium"),
            "needs_ticket": result.get("needs_ticket", False),
            "needs_description": result.get("needs_description", False),
            "create_ticket": result.get("create_ticket", False),
            "detected_services": result.get("detected_services", []),
            "next_issue_options": result.get("next_issue_options", []),
            "knowledge_retrieved": result.get("knowledge_retrieved", False),
            "knowledge_confidence": result.get("knowledge_confidence", 0.0),
            "knowledge_source": result.get("knowledge_source", ""),
            "knowledge_learned": result.get("knowledge_learned", False),
            "knowledge_source_url": result.get("knowledge_source_url", ""),
            "error": False
        })

    except Exception as e:
        print(f"Unexpected error in /chat route: {e}")
        return jsonify({
            "reply": "We are experiencing technical difficulties. Please try again shortly.",
            "resolved": False,
            "ticket_id": None,
            "error": True
        }), 500


# =========================
# Tickets GET route
# returns all open and
# in progress tickets
# =========================
@app.route("/tickets", methods=["GET"])
def tickets():
    try:
        ticket_list = get_open_tickets()
        if ticket_list is None:
            return jsonify({
                "error": True,
                "message": "Unable to retrieve tickets at this time.",
                "tickets": []
            }), 500

        return jsonify({
            "error": False,
            "tickets": ticket_list
        })

    except Exception as e:
        print(f"Unexpected error in /tickets route: {e}")
        return jsonify({
            "error": True,
            "message": "Unable to retrieve tickets at this time.",
            "tickets": []
        }), 500


# =========================
# Tickets update POST route
# updates a ticket status
# =========================
@app.route("/tickets/update", methods=["POST"])
def tickets_update():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "error": True,
                "message": "Invalid request. Please send a valid JSON body."
            }), 400

        ticket_id = data.get("ticket_id")
        new_status = data.get("status")

        if not ticket_id or not new_status:
            return jsonify({
                "error": True,
                "message": "ticket_id and status are required."
            }), 400

        if not isinstance(ticket_id, int) or ticket_id <= 0:
            return jsonify({
                "error": True,
                "message": "ticket_id must be a valid positive number."
            }), 400

        valid_statuses = ["Open", "In Progress", "Resolved", "Closed"]
        if new_status not in valid_statuses:
            return jsonify({
                "error": True,
                "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }), 400

        update_result = update_ticket_status(ticket_id, new_status)
        if update_result == "not_found":
            return jsonify({
                "error": True,
                "message": f"Ticket #{ticket_id} was not found."
            }), 404

        if update_result != "updated":
            return jsonify({
                "error": True,
                "message": "Unable to update ticket at this time."
            }), 500

        return jsonify({
            "error": False,
            "message": f"Ticket #{ticket_id} updated to {new_status}."
        })

    except Exception as e:
        print(f"Unexpected error in /tickets/update route: {e}")
        return jsonify({
            "error": True,
            "message": "Unable to update ticket at this time."
        }), 500


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False") == "True"
    app.run(debug=debug_mode)
