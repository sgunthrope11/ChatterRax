import html
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in project requirements
    load_dotenv = None


_ROOT_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_ROOT_DIR / ".env")


def _enabled():
    return os.environ.get("TICKET_EMAIL_ENABLED", "False").lower() == "true"


def _split_recipients(value):
    return [
        item.strip()
        for item in str(value or "").replace(";", ",").split(",")
        if item.strip()
    ]


def _smtp_port():
    try:
        return int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        return 587


def _ticket_admin_url():
    explicit_url = os.environ.get("TICKET_ADMIN_URL", "").strip()
    if explicit_url:
        return explicit_url

    public_url = os.environ.get("APP_PUBLIC_URL", "").strip().rstrip("/")
    if public_url:
        return f"{public_url}/admin"
    return ""


def _build_ticket_email(
    ticket_id,
    user_name,
    user_email,
    user_department,
    description,
    priority,
    service="",
    intent="",
    session_id=None,
    admin_url="",
):
    subject = f"ChatterRax Ticket #{ticket_id} - {str(priority or 'medium').title()}"
    lines = [
        "A new ChatterRax ticket was created.",
        "",
        f"Ticket ID: {ticket_id}",
        f"Priority: {priority or 'medium'}",
        f"Description: {str(description or '').strip()}",
        "",
        "Admin Link",
        admin_url or "Not configured. Set TICKET_ADMIN_URL to your Railway admin page link.",
        "",
        "Routing",
        f"Service: {service or 'unknown'}",
        f"Intent: {intent or 'unknown'}",
        f"Session ID: {session_id or 'unknown'}",
        "",
        "User",
        f"Name: {user_name}",
        f"Email: {user_email}",
        f"Department: {user_department}",
    ]
    body = "\n".join(lines)
    html_link = (
        f'<p><a href="{html.escape(admin_url)}">Open ChatterRax Admin</a></p>'
        if admin_url
        else "<p>Admin link is not configured. Set TICKET_ADMIN_URL.</p>"
    )
    html_body = f"""
    <html>
      <body>
        <p>A new ChatterRax ticket was created.</p>
        <p>
          <strong>Ticket ID:</strong> {html.escape(str(ticket_id))}<br>
          <strong>Priority:</strong> {html.escape(str(priority or "medium"))}<br>
          <strong>Description:</strong> {html.escape(str(description or "").strip())}
        </p>
        {html_link}
        <p>
          <strong>Service:</strong> {html.escape(str(service or "unknown"))}<br>
          <strong>Intent:</strong> {html.escape(str(intent or "unknown"))}<br>
          <strong>Session ID:</strong> {html.escape(str(session_id or "unknown"))}
        </p>
        <p>
          <strong>User:</strong><br>
          Name: {html.escape(str(user_name or ""))}<br>
          Email: {html.escape(str(user_email or ""))}<br>
          Department: {html.escape(str(user_department or ""))}
        </p>
      </body>
    </html>
    """
    return subject, body, html_body


def _build_message(sender, recipient, subject, body, html_body):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_ticket_created_email(
    ticket_id,
    user_name,
    user_email,
    user_department,
    description,
    priority,
    service="",
    intent="",
    session_id=None,
):
    if not _enabled():
        return False, "disabled"

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = _smtp_port()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", username).strip()
    recipients = _split_recipients(os.environ.get("TICKET_EMAIL_TO", ""))
    use_tls = os.environ.get("SMTP_USE_TLS", "True").lower() == "true"
    admin_url = _ticket_admin_url()

    if not host or not port or not username or not password or not sender or not recipients:
        return False, "missing_smtp_config"

    subject, body, html_body = _build_ticket_email(
        ticket_id=ticket_id,
        user_name=user_name,
        user_email=user_email,
        user_department=user_department,
        description=description,
        priority=priority,
        service=service,
        intent=intent,
        session_id=session_id,
        admin_url=admin_url,
    )

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            failed_recipients = []
            sent_count = 0
            for recipient in recipients:
                message = _build_message(sender, recipient, subject, body, html_body)
                refused = smtp.send_message(message) or {}
                if refused:
                    failed_recipients.append(recipient)
                else:
                    sent_count += 1

        if failed_recipients:
            failed = ", ".join(failed_recipients)
            return sent_count > 0, f"failed_recipients: {failed}"
        return sent_count == len(recipients), ""
    except Exception as exc:
        return False, str(exc)
