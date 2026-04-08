try:
    from db_service import create_ticket, create_chat_session, link_ticket_to_session, save_chat_message
    from connection import get_connection
except ModuleNotFoundError:
    from .db_service import create_ticket, create_chat_session, link_ticket_to_session, save_chat_message
    from .connection import get_connection
from datetime import datetime

# =========================
# Log file setup
# =========================
LOG_FILE = "test_log.txt"

def write_log(message):
    """
    Writes a message to both the terminal and the log file
    with a timestamp on every line
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    print(formatted)
    with open(LOG_FILE, "a") as f:
        f.write(formatted + "\n")

# =========================
# Helper - show all tables
# in one single connection
# =========================
def show_all_tables():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        tables = {
            "Users": """
                SELECT UserID, UserName, Email, Department, CreatedAt
                FROM Users
            """,
            "Tickets": """
                SELECT TicketID, UserID, Priority, Description, Status, CreatedAt
                FROM Tickets
            """,
            "Chat Sessions": """
                SELECT SessionID, UserID, TicketID, SessionStatus, StartTime
                FROM Chat_Sessions
            """,
            "Chat Messages": """
                SELECT MessageID, SessionID, Sender, MessageText, SentAt
                FROM Chat_Messages
            """
        }

        for table_name, query in tables.items():
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]

            write_log(f"\n--- {table_name} ---")
            write_log(" | ".join(columns))
            write_log("-" * 60)

            if rows:
                for row in rows:
                    write_log(" | ".join(str(value) for value in row))
            else:
                write_log("No records found.")

    except Exception as e:
        write_log(f"Error fetching tables: {e}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# Helper - get or create
# a test user automatically
# matched to your schema
# =========================
def get_or_create_test_user():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if seed users already exist
        cursor.execute(
            "SELECT UserID FROM Users WHERE Email = ?",
            ("alex.johnson@email.com",)
        )
        row = cursor.fetchone()

        if row:
            write_log(f"Seed users already exist. Using UserID: {row[0]}")
            return row[0]
        else:
            # Insert all seed users matched to your schema
            users = [
                ("AlexJohnson", "alex.johnson@email.com", "IT"),
                ("JaneSmith", "jane.smith@email.com", "HR"),
                ("MikeBrown", "mike.brown@email.com", "IT"),
                ("EmilyDavis", "emily.davis@email.com", "Finance"),
                ("ChrisWilson", "chris.wilson@email.com", "Support"),
                ("SarahMiller", "sarah.miller@email.com", "Marketing"),
                ("DavidClark", "david.clark@email.com", "IT"),
                ("OliviaJames", "olivia.james@email.com", "Support")
            ]

            for user in users:
                cursor.execute(
                    """
                    INSERT INTO Users (UserName, Email, Department)
                    VALUES (?, ?, ?)
                    """,
                    user
                )
                write_log(f"Created user: {user[0]} | {user[2]} department")

            conn.commit()
            write_log("All seed users created successfully.")

            # Return AlexJohnson's UserID for testing
            cursor.execute(
                "SELECT UserID FROM Users WHERE Email = ?",
                ("alex.johnson@email.com",)
            )
            user_id = cursor.fetchone()[0]
            write_log(f"Test will run as UserID: {user_id}")
            return user_id

    except Exception as e:
        write_log(f"Error getting or creating test user: {e}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# Helper - validate user
# exists before testing
# =========================
def validate_user_exists(user_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT UserID, UserName, Department FROM Users WHERE UserID = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            write_log(f"Validated user: {row[1]} | Department: {row[2]} | UserID: {row[0]}")
            return True
        else:
            write_log(f"UserID {user_id} does not exist in database.")
            return False

    except Exception as e:
        write_log(f"Error validating user: {e}")
        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def main():
    # =========================
    # Start log session
    # =========================
    write_log("=" * 60)
    write_log("TEST SESSION STARTED")
    write_log("=" * 60)

    # =========================
    # Get or create seed users
    # =========================
    test_user_id = get_or_create_test_user()

    if not test_user_id:
        write_log("Could not get or create test user. Stopping test.")
        return

    # =========================
    # Validate user exists
    # =========================
    if not validate_user_exists(test_user_id):
        write_log("User validation failed. Stopping test.")
        return

    # =========================
    # Test create_ticket
    # =========================
    write_log("\nTesting create_ticket:")

    ticket_id = create_ticket(
        user_id=test_user_id,
        description="Cannot login to account",
        priority="high"
    )

    if ticket_id:
        write_log(f"Created TicketID: {ticket_id}")
    else:
        write_log("Ticket creation failed")

    # =========================
    # Test create_chat_session
    # =========================
    write_log("\nTesting create_chat_session:")

    session_id = create_chat_session(
        user_id=test_user_id,
        ticket_id=ticket_id
    )

    if session_id:
        write_log(f"Created SessionID: {session_id}")
    else:
        write_log("Session creation failed")

    # =========================
    # Test save_chat_message
    # =========================
    write_log("\nTesting save_chat_message:")

    if session_id:
        result1 = save_chat_message(session_id, "user", "I cannot log into my account.")
        result2 = save_chat_message(session_id, "bot", "Have you tried resetting your password?")
        result3 = save_chat_message(session_id, "user", "Yes I tried but the reset link is not working.")
        result4 = save_chat_message(session_id, "bot", "Please clear your cache and try again.")

        if result1 and result2 and result3 and result4:
            write_log("All chat messages saved successfully.")
        else:
            write_log("One or more messages failed to save.")

    # =========================
    # Test a session without
    # a ticket - unresolved
    # =========================
    write_log("\nTesting unresolved session with no ticket:")

    unresolved_session_id = create_chat_session(
        user_id=test_user_id,
        ticket_id=None
    )

    if unresolved_session_id:
        write_log(f"Created unresolved SessionID: {unresolved_session_id}")
        save_chat_message(unresolved_session_id, "user", "I need help with something unusual.")
        save_chat_message(unresolved_session_id, "bot", "I was not able to resolve your issue, creating a ticket for an admin.")
        write_log("Unresolved session messages saved.")

        unresolved_ticket_id = create_ticket(
            user_id=test_user_id,
            description="I need help with something unusual.",
            priority="low"
        )
        write_log(f"Ticket created for unresolved session: TicketID {unresolved_ticket_id}")

        if unresolved_ticket_id and link_ticket_to_session(unresolved_session_id, unresolved_ticket_id):
            write_log(f"Linked SessionID {unresolved_session_id} to TicketID {unresolved_ticket_id}")
        else:
            write_log("Failed to link unresolved session to its ticket.")

    # =========================
    # Test invalid inputs
    # =========================
    write_log("\nTesting invalid inputs:")
    if session_id:
        save_chat_message(session_id, "admin", "This should fail - invalid sender")
        save_chat_message(session_id, "user", "")
        save_chat_message(session_id, "user", "   ")

    # =========================
    # Show all tables in
    # one single connection
    # =========================
    write_log("\nFetching all database records:")
    show_all_tables()

    # =========================
    # End log session
    # =========================
    write_log("\n" + "=" * 60)
    write_log("TEST SESSION ENDED")
    write_log("=" * 60 + "\n")


if __name__ == "__main__":
    main()
