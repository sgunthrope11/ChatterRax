-- Generated from the live Chatbot_Ticketing_SYS database on 2026-04-07
-- This file reflects the current deployed schema structure.

IF OBJECT_ID('dbo.UserTicketDetails', 'V') IS NOT NULL
    DROP VIEW dbo.UserTicketDetails;
GO

IF OBJECT_ID('dbo.GetActiveTicketsByUser', 'P') IS NOT NULL
    DROP PROCEDURE dbo.GetActiveTicketsByUser;
GO

IF OBJECT_ID('dbo.Chat_Messages', 'U') IS NOT NULL
    DROP TABLE dbo.Chat_Messages;
GO

IF OBJECT_ID('dbo.Chat_Sessions', 'U') IS NOT NULL
    DROP TABLE dbo.Chat_Sessions;
GO

IF OBJECT_ID('dbo.Tickets', 'U') IS NOT NULL
    DROP TABLE dbo.Tickets;
GO

IF OBJECT_ID('dbo.Users', 'U') IS NOT NULL
    DROP TABLE dbo.Users;
GO

CREATE TABLE dbo.Users (
    UserID INT IDENTITY(1,1) NOT NULL,
    UserName NVARCHAR(50) NOT NULL,
    Email VARCHAR(100) NOT NULL,
    Department NVARCHAR(50) NOT NULL,
    CreatedAt DATETIME NULL CONSTRAINT DF_Users_CreatedAt DEFAULT (GETDATE()),
    CONSTRAINT PK_Users PRIMARY KEY CLUSTERED (UserID),
    CONSTRAINT UQ_Users_Email UNIQUE NONCLUSTERED (Email)
);
GO

CREATE TABLE dbo.Tickets (
    TicketID INT IDENTITY(1,1) NOT NULL,
    UserID INT NOT NULL,
    Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_Tickets_Priority DEFAULT ('low'),
    Description NVARCHAR(MAX) NOT NULL,
    Status VARCHAR(20) NULL CONSTRAINT DF_Tickets_Status DEFAULT ('Open'),
    CreatedAt DATETIME NULL CONSTRAINT DF_Tickets_CreatedAt DEFAULT (GETDATE()),
    UpdatedAt DATETIME NULL CONSTRAINT DF_Tickets_UpdatedAt DEFAULT (GETDATE()),
    CONSTRAINT PK_Tickets PRIMARY KEY CLUSTERED (TicketID),
    CONSTRAINT FK_TICKETS_USERS FOREIGN KEY (UserID) REFERENCES dbo.Users(UserID)
);
GO

CREATE TABLE dbo.Chat_Sessions (
    SessionID INT IDENTITY(1,1) NOT NULL,
    UserID INT NOT NULL,
    TicketID INT NULL,
    StartTime DATETIME NULL CONSTRAINT DF_ChatSessions_StartTime DEFAULT (GETDATE()),
    EndTime DATETIME NULL CONSTRAINT DF_ChatSessions_EndTime DEFAULT (GETDATE()),
    SessionStatus NVARCHAR(20) NULL CONSTRAINT DF_ChatSessions_SessionStatus DEFAULT ('Active'),
    CONSTRAINT PK_Chat_Sessions PRIMARY KEY CLUSTERED (SessionID),
    CONSTRAINT FK_ChatSessions_Users FOREIGN KEY (UserID) REFERENCES dbo.Users(UserID),
    CONSTRAINT FK_ChatSessions_Tickets FOREIGN KEY (TicketID) REFERENCES dbo.Tickets(TicketID)
);
GO

CREATE TABLE dbo.Chat_Messages (
    MessageID INT IDENTITY(1,1) NOT NULL,
    SessionID INT NOT NULL,
    Sender NVARCHAR(10) NOT NULL,
    MessageText NVARCHAR(MAX) NOT NULL,
    SentAt DATETIME NULL CONSTRAINT DF_ChatMessages_SentAt DEFAULT (GETDATE()),
    CONSTRAINT PK_Chat_Messages PRIMARY KEY CLUSTERED (MessageID),
    CONSTRAINT FK_ChatMessages_ChatSessions FOREIGN KEY (SessionID) REFERENCES dbo.Chat_Sessions(SessionID)
);
GO

CREATE NONCLUSTERED INDEX idx_Users_Username
ON dbo.Users (UserName);
GO

CREATE NONCLUSTERED INDEX idx_Tickets_UserID
ON dbo.Tickets (UserID);
GO

CREATE NONCLUSTERED INDEX idx_Tickets_Status
ON dbo.Tickets (Status);
GO

CREATE NONCLUSTERED INDEX idx_Tickets_UserID_Status
ON dbo.Tickets (UserID, Status);
GO

CREATE NONCLUSTERED INDEX idx_ChatSessions_UserID
ON dbo.Chat_Sessions (UserID);
GO

CREATE NONCLUSTERED INDEX idx_ChatSessions_TicketID
ON dbo.Chat_Sessions (TicketID);
GO

CREATE NONCLUSTERED INDEX idx_ChatMessages_SessionID
ON dbo.Chat_Messages (SessionID);
GO

CREATE NONCLUSTERED INDEX idx_ChatMessages_Sender
ON dbo.Chat_Messages (Sender);
GO

CREATE VIEW dbo.UserTicketDetails AS
SELECT
    u.UserName,
    u.Email,
    u.Department,
    t.TicketID,
    t.Priority,
    t.Description,
    t.Status,
    t.CreatedAt,
    t.UpdatedAt
FROM dbo.Users AS u
JOIN dbo.Tickets AS t
    ON u.UserID = t.UserID;
GO

CREATE PROCEDURE dbo.GetActiveTicketsByUser
    @UserID INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        TicketID,
        Priority,
        Description,
        Status,
        CreatedAt,
        UpdatedAt
    FROM dbo.Tickets
    WHERE UserID = @UserID
      AND Status IN ('Open', 'In Progress');
END;
GO
