import pyodbc

try:
    from backend.db.connection import get_connection
except ModuleNotFoundError:
    from .connection import get_connection


SUMMARY_MESSAGE_PREFIX = "[THREAD_SUMMARY]"


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
        if conn:
            conn.rollback()
        print("Error creating chat session:", e)
        return None

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


def get_latest_session_summary(session_id):
    """
    Returns the latest persisted thread summary for a session, or an empty string.
    Summaries are stored inside Chat_Messages using the normal SQL flow with a
    reserved message prefix so no extra table is required.
    """
    if not isinstance(session_id, int) or session_id <= 0:
        return ""

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        base_query = """
        SELECT TOP (1) MessageText
        FROM Chat_Messages
        WHERE SessionID = ?
          AND Sender = 'bot'
          AND LEFT(MessageText, ?) = ?
        """
        params = (session_id, len(SUMMARY_MESSAGE_PREFIX), SUMMARY_MESSAGE_PREFIX)
        order_variants = (
            "ORDER BY MessageID DESC",
            "ORDER BY SentAt DESC, MessageID DESC",
            "ORDER BY SentAt DESC",
        )

        row = None
        for order_clause in order_variants:
            try:
                cursor.execute(f"{base_query}\n{order_clause}", params)
                row = cursor.fetchone()
                break
            except pyodbc.Error:
                continue

        if not row or not str(row[0] or "").strip():
            return ""

        return str(row[0]).strip()[len(SUMMARY_MESSAGE_PREFIX):].strip()

    except pyodbc.Error as e:
        print("Error fetching session summary:", e)
        return ""

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_session_summary(session_id, summary_text):
    """
    Persists a compact thread summary into Chat_Messages using a reserved prefix.
    Duplicate summaries are skipped to avoid polluting the transcript.
    """
    summary_text = str(summary_text or "").strip()
    if not isinstance(session_id, int) or session_id <= 0 or not summary_text:
        return False

    existing_summary = get_latest_session_summary(session_id)
    if existing_summary == summary_text:
        return True

    return save_chat_message(
        session_id,
        "bot",
        f"{SUMMARY_MESSAGE_PREFIX} {summary_text}",
    )


def get_chat_messages(session_id, limit=None, connection=None):
    """
    Returns chat messages for one session ordered oldest -> newest.
    When a connection is supplied, it is reused so callers can read
    uncommitted test data inside a transaction.
    """
    if not isinstance(session_id, int) or session_id <= 0:
        return []

    owns_connection = connection is None
    conn = connection
    cursor = None
    try:
        if conn is None:
            conn = get_connection()
        cursor = conn.cursor()

        top_clause = ""
        params = []
        if isinstance(limit, int) and limit > 0:
            top_clause = "TOP (?) "
            params.append(limit)

        base_query = f"""
        SELECT {top_clause}Sender, MessageText
        FROM Chat_Messages
        WHERE SessionID = ?
          AND LEFT(MessageText, ?) <> ?
        """
        params.append(session_id)
        params.extend([len(SUMMARY_MESSAGE_PREFIX), SUMMARY_MESSAGE_PREFIX])

        order_variants = (
            "ORDER BY MessageID DESC",
            "ORDER BY CreatedAt DESC, MessageID DESC",
            "ORDER BY SentAt DESC, MessageID DESC",
            "ORDER BY CreatedAt DESC",
            "ORDER BY SentAt DESC",
        )

        rows = None
        for order_clause in order_variants:
            try:
                cursor.execute(f"{base_query}\n{order_clause}", tuple(params))
                rows = cursor.fetchall()
                break
            except pyodbc.Error:
                continue

        if rows is None:
            return []

        messages = [
            {
                "sender": str(row[0] or "").strip().lower(),
                "message": str(row[1] or "").strip(),
            }
            for row in reversed(rows)
            if row and str(row[1] or "").strip()
        ]
        return messages

    except pyodbc.Error as e:
        print("Error fetching chat messages:", e)
        return []

    finally:
        if cursor:
            cursor.close()
        if owns_connection and conn:
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
        if conn:
            conn.rollback()
        print("Error updating ticket status:", e)
        return "error"

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
