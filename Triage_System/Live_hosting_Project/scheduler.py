import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def run_cleanup():
    """
    Delete old data while keeping the 15 most recent tickets and everything linked to them.
    Runs inside a single transaction; rolls back entirely on any error.

    Deletion order respects foreign key constraints:
      1. Chat_Messages for sessions linked to non-kept tickets
      2. Chat_Messages for ticketless sessions older than 7 days
      3. Chat_Sessions linked to non-kept tickets
      4. Ticketless Chat_Sessions older than 7 days
      5. Tickets not in the kept set
      6. Users with no remaining Tickets or Chat_Sessions
    """
    try:
        from backend.db.connection import get_connection
    except Exception as exc:
        logger.error(f"[scheduler] Cannot import get_connection: {exc}")
        return

    conn = None
    try:
        conn = get_connection()
        conn.autocommit = False
        cursor = conn.cursor()

        # Step 1: Identify the 15 most recent tickets — never touch these.
        cursor.execute(
            "SELECT ticket_id FROM tickets ORDER BY created_at DESC LIMIT 15"
        )
        kept_ids = [row[0] for row in cursor.fetchall()]

        if not kept_ids:
            logger.info("[scheduler] Cleanup: no tickets in database, nothing to clean.")
            conn.commit()
            return

        placeholders = ",".join(["%s"] * len(kept_ids))

        # Step 2: Delete Chat_Messages linked (via session) to non-kept tickets.
        cursor.execute(
            f"""
            DELETE FROM chat_messages
            WHERE session_id IN (
                SELECT session_id FROM chat_sessions
                WHERE ticket_id IS NOT NULL
                  AND ticket_id NOT IN ({placeholders})
            )
            """,
            kept_ids,
        )
        deleted_msgs_ticket = cursor.rowcount

        # Step 3: Delete Chat_Messages for ticketless sessions older than 7 days.
        cursor.execute(
            """
            DELETE FROM chat_messages
            WHERE session_id IN (
                SELECT session_id FROM chat_sessions
                WHERE ticket_id IS NULL
                  AND start_time < NOW() - INTERVAL '7 days'
            )
            """
        )
        deleted_msgs_old = cursor.rowcount

        # Step 4: Delete Chat_Sessions linked to non-kept tickets.
        cursor.execute(
            f"""
            DELETE FROM chat_sessions
            WHERE ticket_id IS NOT NULL
              AND ticket_id NOT IN ({placeholders})
            """,
            kept_ids,
        )
        deleted_sessions_ticket = cursor.rowcount

        # Step 5: Delete ticketless Chat_Sessions older than 7 days.
        cursor.execute(
            """
            DELETE FROM chat_sessions
            WHERE ticket_id IS NULL
              AND start_time < NOW() - INTERVAL '7 days'
            """
        )
        deleted_sessions_old = cursor.rowcount

        # Step 6: Delete Tickets not in the kept set.
        cursor.execute(
            f"DELETE FROM tickets WHERE ticket_id NOT IN ({placeholders})",
            kept_ids,
        )
        deleted_tickets = cursor.rowcount

        # Step 7: Delete Users with no remaining Tickets or Chat_Sessions.
        cursor.execute(
            """
            DELETE FROM users
            WHERE user_id NOT IN (SELECT DISTINCT user_id FROM tickets)
              AND user_id NOT IN (SELECT DISTINCT user_id FROM chat_sessions)
            """
        )
        deleted_users = cursor.rowcount

        conn.commit()
        logger.info(
            "[scheduler] Cleanup succeeded — "
            f"chat_messages(ticket-linked): {deleted_msgs_ticket}, "
            f"chat_messages(ticketless-old): {deleted_msgs_old}, "
            f"chat_sessions(ticket-linked): {deleted_sessions_ticket}, "
            f"chat_sessions(ticketless-old): {deleted_sessions_old}, "
            f"tickets: {deleted_tickets}, "
            f"users: {deleted_users}"
        )

    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error(f"[scheduler] Cleanup failed and rolled back: {exc}")

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def start_scheduler():
    """Start the background scheduler. Weekly cleanup runs every Sunday at midnight.
    An initial cleanup fires 60 seconds after startup so the first request is not delayed."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_cleanup,
        CronTrigger(day_of_week="sun", hour=0, minute=0),
        id="weekly_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        run_cleanup,
        "date",
        run_date=datetime.now() + timedelta(seconds=60),
        id="startup_cleanup",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
