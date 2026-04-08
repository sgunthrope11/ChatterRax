import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

try:
    from bot_logic import handle_message
    from db_service import (
        create_chat_session,
        create_ticket,
        get_open_tickets,
        link_ticket_to_session,
        save_chat_message,
        update_ticket_status,
    )
except ModuleNotFoundError:
    from .bot_logic import handle_message
    from .db_service import (
        create_chat_session,
        create_ticket,
        get_open_tickets,
        link_ticket_to_session,
        save_chat_message,
        update_ticket_status,
    )

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)


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
        user_id = data.get("user_id", 1)

        if not user_message:
            return jsonify({
                "reply": "Please type a message before sending.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        if not isinstance(user_id, int) or user_id <= 0:
            return jsonify({
                "reply": "Invalid user. Please refresh and try again.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 400

        session_id = create_chat_session(user_id, ticket_id=None)
        if session_id is None:
            return jsonify({
                "reply": "We are experiencing technical difficulties. Please try again shortly.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 500

        user_message_saved = save_chat_message(session_id, "user", user_message)
        if not user_message_saved:
            print(f"Warning: Failed to save user message for session {session_id}")

        result = handle_message(user_message)

        bot_message_saved = save_chat_message(session_id, "bot", result["reply"])
        if not bot_message_saved:
            print(f"Warning: Failed to save bot reply for session {session_id}")

        ticket_id = None
        if not result["resolved"]:
            ticket_id = create_ticket(
                user_id=user_id,
                description=user_message,
                priority="low"
            )
            if ticket_id is None:
                return jsonify({
                    "reply": "We are experiencing technical difficulties. Please try again shortly.",
                    "resolved": False,
                    "ticket_id": None,
                    "error": True
                }), 500

            if not link_ticket_to_session(session_id, ticket_id):
                return jsonify({
                    "reply": "We created your ticket, but could not finish linking the chat session.",
                    "resolved": False,
                    "ticket_id": ticket_id,
                    "error": True
                }), 500

            print(f"Ticket created: #{ticket_id}")

        return jsonify({
            "reply": result["reply"],
            "resolved": result["resolved"],
            "ticket_id": ticket_id,
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
