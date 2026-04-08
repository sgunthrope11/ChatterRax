import pyodbc

try:
    from connection import get_connection
except ModuleNotFoundError:
    from .connection import get_connection

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
# link_ticket_to_session function
# =========================
def link_ticket_to_session(session_id, ticket_id):
    """
    Links an existing ticket to an existing chat session.
    Returns True if successful, False if it fails or no row is updated.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        UPDATE Chat_Sessions
        SET TicketID = ?
        WHERE SessionID = ?
        """

        cursor.execute(query, (ticket_id, session_id))
        if cursor.rowcount == 0:
            print(f"No chat session found for SessionID {session_id}.")
            conn.rollback()
            return False

        conn.commit()
        return True

    except pyodbc.Error as e:
        print("Error linking ticket to chat session:", e)
        return False

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


# =========================
# get_open_tickets function
# =========================
def get_open_tickets():
    """
    Returns all tickets with status Open or In Progress.
    Returns a list of dicts or None if it fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        SELECT t.TicketID, t.UserID, u.UserName, u.Department, t.Priority,
               t.Description, t.Status, t.CreatedAt, t.UpdatedAt
        FROM Tickets t
        JOIN Users u ON t.UserID = u.UserID
        WHERE t.Status IN ('Open', 'In Progress')
        ORDER BY t.CreatedAt DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

        tickets = []
        for row in rows:
            tickets.append(dict(zip(columns, [
                str(value) if not isinstance(value, (int, str, type(None))) else value
                for value in row
            ])))

        return tickets

    except pyodbc.Error as e:
        print("Error fetching open tickets:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# update_ticket_status function
# =========================
def update_ticket_status(ticket_id, new_status):
    """
    Updates the Status and UpdatedAt fields of a ticket.
    Returns "updated", "not_found", or "error".
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
        UPDATE Tickets
        SET Status = ?, UpdatedAt = GETDATE()
        WHERE TicketID = ?
        """

        cursor.execute(query, (new_status, ticket_id))
        if cursor.rowcount == 0:
            print(f"No ticket found for TicketID {ticket_id}.")
            conn.rollback()
            return "not_found"

        conn.commit()
        return "updated"

    except pyodbc.Error as e:
        print("Error updating ticket status:", e)
        return "error"

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
