import pyodbc

try:
    from connection import get_connection
except ModuleNotFoundError:
    from .connection import get_connection


def get_or_create_chat_user(user_name, email, department):
    """
    Finds a user by email or creates one if it does not exist yet.
    Updates the stored name and department when the email already exists.
    Returns the resolved UserID or None if validation/database work fails.
    """
    user_name = str(user_name or "").strip()
    email = str(email or "").strip().lower()
    department = str(department or "").strip()

    if not user_name or not email or not department:
        return None

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT UserID
            FROM Users
            WHERE Email = ?
            """,
            (email,)
        )
        existing_user = cursor.fetchone()
        if existing_user:
            user_id = existing_user[0]
            cursor.execute(
                """
                UPDATE Users
                SET UserName = ?, Department = ?
                WHERE UserID = ?
                """,
                (user_name, department, user_id)
            )
            conn.commit()
            return user_id

        cursor.execute(
            """
            INSERT INTO Users (UserName, Email, Department)
            OUTPUT INSERTED.UserID
            VALUES (?, ?, ?)
            """,
            (user_name, email, department)
        )
        user_id = cursor.fetchone()[0]
        conn.commit()
        return user_id

    except pyodbc.Error as e:
        if conn:
            conn.rollback()
        print("Error resolving chat user:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
# create_ticket_for_session function
# =========================
def create_ticket_for_session(session_id, user_id, description, priority='low'):
    """
    Creates a ticket and links it to an existing session in one transaction.
    Returns the new TicketID or None if any step fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO Tickets (UserID, Priority, Description)
            OUTPUT INSERTED.TicketID
            VALUES (?, ?, ?)
            """,
            (user_id, priority, description)
        )
        ticket_id = cursor.fetchone()[0]

        cursor.execute(
            """
            UPDATE Chat_Sessions
            SET TicketID = ?
            WHERE SessionID = ?
            """,
            (ticket_id, session_id)
        )

        if cursor.rowcount == 0:
            print(f"No chat session found for SessionID {session_id}.")
            conn.rollback()
            return None

        conn.commit()
        return ticket_id

    except pyodbc.Error as e:
        if conn:
            conn.rollback()
        print("Error creating and linking ticket:", e)
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
