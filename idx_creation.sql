-- Index on UserName (frequent search/login)
CREATE NONCLUSTERED INDEX idx_Users_Username
ON Users (UserName);

-- =========================
-- TICKETS TABLE INDEXES
-- =========================

-- Index on UserID (search tickets by user)
CREATE NONCLUSTERED INDEX idx_Tickets_UserID
ON Tickets (UserID);

-- Index on Status (filter tickets like Open, Closed)
CREATE NONCLUSTERED INDEX idx_Tickets_Status
ON Tickets (Status);

-- Composite index (User + Status for faster filtering)
CREATE NONCLUSTERED INDEX idx_Tickets_UserID_Status
ON Tickets (UserID, Status);


-- =========================
-- CHAT_SESSIONS TABLE INDEXES
-- =========================

-- Index on UserID (get sessions for a user)
CREATE NONCLUSTERED INDEX idx_ChatSessions_UserID
ON Chat_Sessions (UserID);

-- Index on TicketID (sessions linked to tickets)
CREATE NONCLUSTERED INDEX idx_ChatSessions_TicketID
ON Chat_Sessions (TicketID);


-- =========================
-- CHAT_MESSAGES TABLE INDEXES
-- =========================

-- Index on SessionID (get messages in a chat session)
CREATE NONCLUSTERED INDEX idx_ChatMessages_SessionID
ON Chat_Messages (SessionID);

-- Index on SenderID (messages by user)
CREATE NONCLUSTERED INDEX idx_ChatMessages_Sender
ON Chat_Messages (Sender);
