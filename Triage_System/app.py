import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

try:
    from bot_logic import handle_message
    from db_service import (
        create_chat_session,
        create_ticket_for_session,
        get_or_create_chat_user,
        get_open_tickets,
        save_chat_message,
        update_ticket_status,
    )
    from status_provider import check_microsoft_public_status
except ModuleNotFoundError:
    from .bot_logic import handle_message
    from .db_service import (
        create_chat_session,
        create_ticket_for_session,
        get_or_create_chat_user,
        get_open_tickets,
        save_chat_message,
        update_ticket_status,
    )
    from .status_provider import check_microsoft_public_status

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
PENDING_TICKET_REQUESTS = {}
CONVERSATION_HISTORY = {}
ACTIVE_SESSIONS = {}        # keyed by conversation key; reused within one browser tab/session
MAX_HISTORY_TURNS = 6
_STATE_LOCK = threading.Lock()


def _conversation_key(user_email, client_session_id=None):
    if client_session_id:
        return f"{user_email}::{client_session_id}"
    return user_email


def _append_conversation_turn(conversation_key, sender, message_text):
    with _STATE_LOCK:
        history = CONVERSATION_HISTORY.setdefault(conversation_key, [])
        history.append({
            "sender": sender,
            "message": str(message_text or "").strip(),
        })
        CONVERSATION_HISTORY[conversation_key] = history[-MAX_HISTORY_TURNS:]


# =========================
# Navigation routes
# =========================
@app.route("/")
def home():
    return redirect(url_for("chatbot_page"))


@app.route("/chatbot")
def chatbot_page():
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
    except Exception as e:
        print(f"Unexpected error in /status route: {e}")
        return jsonify({
            "issue_found": False,
            "summary": "Unable to retrieve Microsoft public status right now.",
            "service": request.args.get("service") or "microsoft 365",
            "status_available": False,
            "stale": False,
            "error": True
        }), 500


# =========================
# Chat route
# main endpoint that
# processes messages
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    try:
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
                "reply": "Please provide your name, email, and department before starting the chat.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        if "@" not in user_email or user_email.startswith("@") or user_email.endswith("@"):
            return jsonify({
                "reply": "Please enter a valid email address before sending your message.",
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
            conversation_history = CONVERSATION_HISTORY.get(conversation_key, [])[-MAX_HISTORY_TURNS:]
        result = handle_message(
            user_message,
            awaiting_ticket_detail=bool(pending_ticket_request),
            conversation_history=conversation_history,
        )

        bot_message_saved = save_chat_message(session_id, "bot", result["reply"])
        if not bot_message_saved:
            print(f"Warning: Failed to save bot reply for session {session_id}")

        _append_conversation_turn(conversation_key, "user", user_message)
        _append_conversation_turn(conversation_key, "bot", result["reply"])

        ticket_id = None
        if result.get("needs_ticket") and result.get("needs_description"):
            if pending_ticket_request:
                pending_ticket_request["latest_prompt"] = result["reply"]
            else:
                with _STATE_LOCK:
                    PENDING_TICKET_REQUESTS[conversation_key] = {
                        "initial_message": user_message,
                        "service": result.get("service"),
                    }
        else:
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
            "detected_services": result.get("detected_services", []),
            "status_checked": result.get("status_checked", False),
            "status_summary": result.get("status_summary", ""),
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
