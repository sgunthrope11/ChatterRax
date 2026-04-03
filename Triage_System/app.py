import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from bot_logic import handle_message
from db_service import create_ticket, create_chat_session, save_chat_message, get_open_tickets, update_ticket_status

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Home route - serves the chat interface
@app.route("/")
def index():
    return render_template("index.html")

# Admin route - serves the admin interface
@app.route("/admin")
def admin():
    return render_template("admin.html")

# Chat route - main endpoint that processes messages
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        user_id = data.get("user_id", 1)

        # Step 1: create a chat session
        session_id = create_chat_session(user_id, ticket_id=None)
        if session_id is None:
            return jsonify({
                "reply": "We are experiencing technical difficulties. Please try again shortly.",
                "resolved": False,
                "ticket_id": None,
                "error": True
            }), 500

        # Step 2: save the user message
        save_chat_message(session_id, "user", user_message)

        # Step 3: run through bot logic
        result = handle_message(user_message)

        # Step 4: save the bot reply
        save_chat_message(session_id, "bot", result["reply"])

        # Step 5: if not resolved create a ticket
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
            print(f"Ticket created: #{ticket_id}")

        return jsonify({
            "reply": result["reply"],
            "resolved": result["resolved"],
            "ticket_id": ticket_id,
            "error": False
        })

    except Exception as e:
        print(f"Error in /chat route: {e}")
        return jsonify({
            "reply": "We are experiencing technical difficulties. Please try again shortly.",
            "resolved": False,
            "ticket_id": None,
            "error": True
        }), 500

# Tickets GET route - returns all open and in progress tickets
@app.route("/tickets", methods=["GET"])
def tickets():
    try:
        ticket_list = get_open_tickets()
        if ticket_list is None:
            return jsonify({
                "error": True,
                "message": "Unable to retrieve tickets at this time."
            }), 500
        return jsonify({
            "error": False,
            "tickets": ticket_list
        })
    except Exception as e:
        print(f"Error in /tickets route: {e}")
        return jsonify({
            "error": True,
            "message": "Unable to retrieve tickets at this time."
        }), 500

# Tickets update POST route - updates a ticket status
@app.route("/tickets/update", methods=["POST"])
def tickets_update():
    try:
        data = request.get_json()
        ticket_id = data.get("ticket_id")
        new_status = data.get("status")

        if not ticket_id or not new_status:
            return jsonify({
                "error": True,
                "message": "ticket_id and status are required."
            }), 400

        valid_statuses = ["Open", "In Progress", "Resolved"]
        if new_status not in valid_statuses:
            return jsonify({
                "error": True,
                "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }), 400

        success = update_ticket_status(ticket_id, new_status)
        if not success:
            return jsonify({
                "error": True,
                "message": "Unable to update ticket at this time."
            }), 500

        return jsonify({
            "error": False,
            "message": f"Ticket #{ticket_id} updated to {new_status}."
        })

    except Exception as e:
        print(f"Error in /tickets/update route: {e}")
        return jsonify({
            "error": True,
            "message": "Unable to update ticket at this time."
        }), 500

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False") == "True"
    app.run(debug=debug_mode)