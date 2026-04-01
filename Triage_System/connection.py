import pyodbc

def get_connection():
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost;'
        'DATABASE=Chatbot_ticketing_SYS;'  # replace with your actual DB name
        'Trusted_Connection=yes;'
    )
    return conn

try:
    conn = get_connection()
    print("Connection successful!")
    conn.close()
except Exception as e:
    print("Connection failed:", e)