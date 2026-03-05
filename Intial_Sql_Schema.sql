Create Table Users (
	UserID int primary key identity(1,1),
	UserName nvarchar(50) not null,
	Email varchar(100) not null unique,
	Department NVARCHAR(50) NOT NULL,
	CreatedAt datetime default getdate()
	);
	GO

Create Table Tickets (
	TicketID int primary key identity(1,1),
	UserID int not null,
	Priority nvarchar(20) default 'low' not null,
	Description nvarchar(max) not null,
	Status varchar(20) default 'Open',
	CreatedAt datetime default getdate(),
	UpdatedAt datetime default getdate(),
	CONSTRAINT FK_TICKETS_USERS Foreign Key (UserID) references Users(UserID)
	);
	Go

	Create Table Chat_Sessions (
	SessionID int primary key identity(1,1),
	UserID int not null,
	TicketID int,
	StartTime datetime default getdate(),
	EndTime datetime default getdate(),
	SessionStatus nvarchar(20) default 'Active',
	CONSTRAINT FK_ChatSessions_Users FOREIGN KEY (UserID) REFERENCES Users(UserID),
	CONSTRAINT FK_ChatSessions_Tickets FOREIGN KEY (TicketID) REFERENCES Tickets(TicketID)
	);
	GO

	CREATE TABLE Chat_Messages (
	MessageID int primary key identity(1,1),
	SessionID int not null,
	Sender nvarchar(10) not null,
	MessageText nvarchar(max) not null,
	SentAt datetime default getdate(),
	CONSTRAINT FK_ChatMessages_ChatSessions FOREIGN KEY (SessionID) REFERENCES Chat_Sessions(SessionID)
	);
	GO