import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from bot_logic import handle_message
from db_service import create_ticket, create_chat_session, save_chat_message

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Home route - serves the chat interface
@app.route("/")
def index():
    return render_template("index.html")

# Chat route - main endpoint that processes messages
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    user_id = data.get("user_id", 1)

    # Step 1: create a chat session
    ## session_id = create_chat_session(user_id, ticket_id=None)

    # Step 2: save the user message
    ## save_chat_message(session_id, "user", user_message)

    # Step 3: run through bot logic
    result = handle_message(user_message)

    # Step 4: save the bot reply
    ## save_chat_message(session_id, "bot", result["reply"])


    return jsonify({
        "reply": result["reply"],
        "resolved": result["resolved"]
    })

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False") == "True"
    app.run(debug=debug_mode)