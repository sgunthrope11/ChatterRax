import os

import psycopg2


def get_connection():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return psycopg2.connect(url)


def test_connection():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT version()")
    version = cursor.fetchone()[0]
    print(f"PostgreSQL connection successful. Version: {version}")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    test_connection()
