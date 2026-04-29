-- ChatterRax PostgreSQL schema
-- Executed automatically on every application startup before the scheduler starts.
-- Every statement uses IF NOT EXISTS so this file is fully idempotent:
-- it can be run on a live database with existing data without dropping or truncating anything.

CREATE TABLE IF NOT EXISTS users (
    user_id    SERIAL       PRIMARY KEY,
    user_name  VARCHAR(50)  NOT NULL,
    email      VARCHAR(100) NOT NULL UNIQUE,
    department VARCHAR(50)  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   SERIAL      PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(user_id),
    priority    VARCHAR(20) NOT NULL DEFAULT 'low',
    description TEXT        NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'Open',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id     SERIAL      PRIMARY KEY,
    user_id        INTEGER     NOT NULL REFERENCES users(user_id),
    ticket_id      INTEGER     REFERENCES tickets(ticket_id),
    start_time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time       TIMESTAMPTZ          DEFAULT NULL,
    session_status VARCHAR(20)          DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id   SERIAL      PRIMARY KEY,
    session_id   INTEGER     NOT NULL REFERENCES chat_sessions(session_id),
    sender       VARCHAR(10) NOT NULL,
    message_text TEXT        NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email             ON users(email);
CREATE INDEX IF NOT EXISTS idx_tickets_user_id         ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status          ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_user_id_status  ON tickets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id   ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_ticket_id ON chat_sessions(ticket_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_sender    ON chat_messages(sender);
