-- INSERT USERS
INSERT INTO Users (Username, Email, Department) VALUES
('AlexJohnson', 'alex.johnson@email.com', 'Support'),
('JaneSmith', 'jane.smith@email.com', 'Sales'),
('MikeBrown', 'mike.brown@email.com', 'IT'),
('EmilyDavis', 'emily.davis@email.com', 'HR'),
('ChrisWilson', 'chris.wilson@email.com', 'Support'),
('SarahMiller', 'sarah.miller@email.com', 'Finance'),
('DavidClark', 'david.clark@email.com', 'Sales'),
('OliviaJames', 'olivia.james@email.com', 'Support');

-- INSERT TICKETS
INSERT INTO Tickets (UserID, Priority, Description, Status) VALUES
(1, 'High',   'Cannot login to account',        'Open'),
(2, 'High',   'Payment not going through',       'In Progress'),
(3, 'Medium', 'Website crashing on submit',      'Resolved'),
(4, 'High',   'Password reset not working',      'Open'),
(5, 'Low',    'Error 404 on dashboard',          'Resolved'),
(6, 'Medium', 'Unable to upload files',          'In Progress'),
(7, 'Low',    'Slow loading time',               'Open'),
(8, 'Low',    'Profile not updating',            'Resolved'),
(1, 'High',   'Two-factor issue',                'In Progress'),
(2, 'Medium', 'Email not received',              'Open'),
(3, 'Medium', 'System timeout error',            'Resolved'),
(4, 'High',   'Account locked',                  'In Progress'),
(5, 'Low',    'Feature request: dark mode',      'Open'),
(6, 'Medium', 'Mobile layout broken',            'Resolved'),
(7, 'Low',    'Notifications not working',       'Open'),
(8, 'High',   'Security concern',                'In Progress'),
(1, 'Medium', 'Data not saving',                 'Resolved'),
(2, 'High',   'Login redirect loop',             'Open');

-- INSERT CHAT SESSIONS
INSERT INTO Chat_Sessions (UserID, TicketID, SessionStatus) VALUES
(1, 1,  'Active'),
(2, 2,  'Active'),
(4, 4,  'Active'),
(6, 6,  'Active'),
(7, 7,  'Active'),
(8, 8,  'Closed');

-- INSERT CHAT MESSAGES
INSERT INTO Chat_Messages (SessionID, Sender, MessageText) VALUES
(1, 'User',  'I cannot log into my account.'),
(1, 'Agent', 'Have you tried resetting your password?'),
(2, 'User',  'My payment keeps failing.'),
(2, 'Agent', 'We are checking the issue now.'),
(3, 'User',  'Password reset link is not working.'),
(3, 'Agent', 'Please try again after clearing cache.'),
(4, 'User',  'File upload not working.'),
(4, 'Agent', 'We are fixing this bug.'),
(5, 'User',  'The system is very slow today.'),
(6, 'User',  'My profile changes are not saving.');
GO
-- VIEW (Users + Tickets)
CREATE VIEW UserTicketDetails AS
SELECT
    u.Username,
    u.Email,
    u.Department,
    t.TicketID,
    t.Priority,
    t.Description,
    t.Status,
    t.CreatedAt,
    t.UpdatedAt
FROM Users u
JOIN Tickets t ON u.UserID = t.UserID;
GO
-- STORED PROCEDURE (Active tickets by user)
CREATE PROCEDURE GetActiveTicketsByUser
    @UserID INT
AS
BEGIN
    SELECT
        TicketID,
        Priority,
        Description,
        Status,
        CreatedAt,
        UpdatedAt
    FROM Tickets
    WHERE UserID = @UserID
      AND Status IN ('Open', 'In Progress');
END;