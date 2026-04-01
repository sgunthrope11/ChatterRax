import pyodbc
from connection import get_connection

# =========================
# create_ticket function
# =========================
def create_ticket(user_id, description, priority='low'):
    """
    Creates a new ticket in the Tickets table.
    Returns the new TicketID or None if it fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO Tickets (UserID, Priority, Description)
        OUTPUT INSERTED.TicketID
        VALUES (?, ?, ?)
        """

        cursor.execute(query, (user_id, priority, description))
        ticket_id = cursor.fetchone()[0]
        conn.commit()
        return ticket_id

    except pyodbc.Error as e:
        print("Error creating ticket:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# create_chat_session function
# =========================
def create_chat_session(user_id, ticket_id=None):
    """
    Creates a new chat session in Chat_Sessions table.
    Returns the new SessionID or None if it fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO Chat_Sessions (UserID, TicketID)
        OUTPUT INSERTED.SessionID
        VALUES (?, ?)
        """

        cursor.execute(query, (user_id, ticket_id))
        session_id = cursor.fetchone()[0]
        conn.commit()
        return session_id

    except pyodbc.Error as e:
        print("Error creating chat session:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# save_chat_message function
# =========================
def save_chat_message(session_id, sender, message_text):
    """
    Saves a message into the Chat_Messages table.
    Returns True if successful, False if it fails.
    """
    if sender not in ("user", "bot"):
        print("Invalid sender value. Must be user or bot.")
        return False

    if not message_text or not message_text.strip():
        print("Message text cannot be empty.")
        return False

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO Chat_Messages (SessionID, Sender, MessageText)
        VALUES (?, ?, ?)
        """

        cursor.execute(query, (session_id, sender, message_text.strip()))
        conn.commit()
        return True

    except pyodbc.Error as e:
        print("Error saving chat message:", e)
        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()