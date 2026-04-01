def handle_message(message):
    msg = message.lower()

    # Each keyword maps to a specific helpful response
    keyword_responses = {
        "password": "To reset your password go to the login page and click Forgot Password.",
        "login": "If you cannot log in try clearing your browser cache and cookies then try again.",
        "error": "Please note the error message you are seeing and try restarting the application.",
        "not working": "Please describe what is not working and try restarting the system first.",
        "reset": "To reset your account go to settings and select Reset Account or contact support.",
        "access": "If you are having access issues please verify your permissions with your department admin.",
        "slow": "If the system is running slow try closing other applications and refreshing the page.",
        "crash": "If the application is crashing try restarting it and clearing your temporary files."
    }

    # Check if any keyword appears in the message
    for keyword, reply in keyword_responses.items():
        if keyword in msg:
            return {
                "resolved": True,
                "reply": reply
            }

    # No keyword matched - escalate to admin
    return {
        "resolved": False,
        "reply": "I was not able to resolve your issue, creating a ticket for an admin."
    }
