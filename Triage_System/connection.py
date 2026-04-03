import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    conn = pyodbc.connect(
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
        f'SERVER={os.environ.get("DB_SERVER", "localhost")};'
        f'DATABASE={os.environ.get("DB_NAME", "Chatbot_Ticketing_SYS")};'
        f'Trusted_Connection=yes;'
    )
    return conn