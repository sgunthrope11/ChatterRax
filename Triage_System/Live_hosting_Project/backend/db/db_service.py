import psycopg2

try:
    from backend.db.connection import get_connection
except ModuleNotFoundError:
    from .connection import get_connection


SUMMARY_MESSAGE_PREFIX = "[THREAD_SUMMARY]"


def get_or_create_chat_user(user_name, email, department):
    """
    Finds a user by email or creates one if it does not exist yet.
    Updates the stored name and department when the email already exists.
    Returns the resolved user_id or None if validation/database work fails.
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
            "SELECT user_id FROM users WHERE email = %s",
            (email,),
        )
        existing_user = cursor.fetchone()
        if existing_user:
            user_id = existing_user[0]
            cursor.execute(
                "UPDATE users SET user_name = %s, department = %s WHERE user_id = %s",
                (user_name, department, user_id),
            )
            conn.commit()
            return user_id

        cursor.execute(
            "INSERT INTO users (user_name, email, department) VALUES (%s, %s, %s) RETURNING user_id",
            (user_name, email, department),
        )
        user_id = cursor.fetchone()[0]
        conn.commit()
        return user_id

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error resolving chat user:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def create_chat_session(user_id, ticket_id=None):
    """
    Creates a new chat session in chat_sessions table.
    Returns the new session_id or None if it fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO chat_sessions (user_id, ticket_id) VALUES (%s, %s) RETURNING session_id",
            (user_id, ticket_id),
        )
        session_id = cursor.fetchone()[0]
        conn.commit()
        return session_id

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error creating chat session:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def create_ticket_for_session(session_id, user_id, description, priority='low'):
    """
    Creates a ticket and links it to an existing session in one transaction.
    Returns the new ticket_id or None if any step fails.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO tickets (user_id, priority, description) VALUES (%s, %s, %s) RETURNING ticket_id",
            (user_id, priority, description),
        )
        ticket_id = cursor.fetchone()[0]

        cursor.execute(
            "UPDATE chat_sessions SET ticket_id = %s WHERE session_id = %s",
            (ticket_id, session_id),
        )

        if cursor.rowcount == 0:
            print(f"No chat session found for session_id {session_id}.")
            conn.rollback()
            return None

        conn.commit()
        return ticket_id

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error creating and linking ticket:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_chat_message(session_id, sender, message_text):
    """
    Saves a message into the chat_messages table.
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

        cursor.execute(
            "INSERT INTO chat_messages (session_id, sender, message_text) VALUES (%s, %s, %s)",
            (session_id, sender, message_text.strip()),
        )
        conn.commit()
        return True

    except Exception as e:
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
    Summaries are stored inside chat_messages using the normal SQL flow with a
    reserved message prefix so no extra table is required.
    """
    if not isinstance(session_id, int) or session_id <= 0:
        return ""

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT message_text
            FROM chat_messages
            WHERE session_id = %s
              AND sender = 'bot'
              AND LEFT(message_text, %s) = %s
            ORDER BY message_id DESC
            LIMIT 1
            """,
            (session_id, len(SUMMARY_MESSAGE_PREFIX), SUMMARY_MESSAGE_PREFIX),
        )
        row = cursor.fetchone()

        if not row or not str(row[0] or "").strip():
            return ""

        return str(row[0]).strip()[len(SUMMARY_MESSAGE_PREFIX):].strip()

    except Exception as e:
        print("Error fetching session summary:", e)
        return ""

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_session_summary(session_id, summary_text):
    """
    Persists a compact thread summary into chat_messages using a reserved prefix.
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

        limit_clause = ""
        params = [session_id, len(SUMMARY_MESSAGE_PREFIX), SUMMARY_MESSAGE_PREFIX]
        if isinstance(limit, int) and limit > 0:
            limit_clause = "LIMIT %s"
            params.append(limit)

        cursor.execute(
            f"""
            SELECT sender, message_text
            FROM chat_messages
            WHERE session_id = %s
              AND LEFT(message_text, %s) <> %s
            ORDER BY message_id DESC
            {limit_clause}
            """,
            tuple(params),
        )
        rows = cursor.fetchall()

        messages = [
            {
                "sender": str(row[0] or "").strip().lower(),
                "message": str(row[1] or "").strip(),
            }
            for row in reversed(rows)
            if row and str(row[1] or "").strip()
        ]
        return messages

    except Exception as e:
        print("Error fetching chat messages:", e)
        return []

    finally:
        if cursor:
            cursor.close()
        if owns_connection and conn:
            conn.close()


def get_open_tickets():
    """
    Returns all tickets with status Open or In Progress.
    Returns a list of dicts or None if it fails.
    Column aliases preserve the PascalCase keys the admin frontend expects.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                t.ticket_id   AS "TicketID",
                t.user_id     AS "UserID",
                u.user_name   AS "UserName",
                u.department  AS "Department",
                t.priority    AS "Priority",
                t.description AS "Description",
                t.status      AS "Status",
                t.created_at  AS "CreatedAt",
                t.updated_at  AS "UpdatedAt"
            FROM tickets t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.status IN ('Open', 'In Progress')
            ORDER BY t.created_at DESC
            """
        )
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

        tickets = []
        for row in rows:
            tickets.append(dict(zip(columns, [
                str(value) if not isinstance(value, (int, str, type(None))) else value
                for value in row
            ])))

        return tickets

    except Exception as e:
        print("Error fetching open tickets:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def update_ticket_status(ticket_id, new_status):
    """
    Updates the status and updated_at fields of a ticket.
    Returns "updated", "not_found", or "error".
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE tickets SET status = %s, updated_at = NOW() WHERE ticket_id = %s",
            (new_status, ticket_id),
        )

        if cursor.rowcount == 0:
            print(f"No ticket found for ticket_id {ticket_id}.")
            conn.rollback()
            return "not_found"

        conn.commit()
        return "updated"

    except Exception as e:
        if conn:
            conn.rollback()
        print("Error updating ticket status:", e)
        return "error"

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
