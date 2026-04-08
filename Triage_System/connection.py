import os

import pyodbc
from dotenv import load_dotenv

load_dotenv()


def _bool_setting(name, default):
    value = os.environ.get(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _driver_candidates():
    configured_driver = os.environ.get("DB_DRIVER")
    if configured_driver:
        return [configured_driver]

    installed = set(pyodbc.drivers())
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    return [driver for driver in preferred if driver in installed]


def _server_candidates():
    base_server = os.environ.get("DB_SERVER", "localhost").strip()
    machine_name = os.environ.get("COMPUTERNAME", "").strip()

    candidates = [
        base_server,
        ".",
        "(local)",
    ]

    if machine_name:
        candidates.extend([
            machine_name,
            f"{machine_name}\\MSSQLSERVER",
            f"{machine_name}\\SQLEXPRESS",
        ])

    if base_server == "localhost":
        candidates.extend([
            "localhost\\MSSQLSERVER",
            "localhost\\SQLEXPRESS",
        ])

    # Keep order but remove duplicates/empties.
    unique = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _build_connection_string(driver, server):
    database = os.environ.get("DB_NAME", "Chatbot_Ticketing_SYS")
    timeout = os.environ.get("DB_TIMEOUT", "5")

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        "Trusted_Connection=yes",
    ]

    if driver != "SQL Server":
        parts.append(f"Encrypt={'yes' if _bool_setting('DB_ENCRYPT', False) else 'no'}")
        parts.append(
            f"TrustServerCertificate={'yes' if _bool_setting('DB_TRUST_SERVER_CERTIFICATE', True) else 'no'}"
        )

    parts.append(f"Connection Timeout={timeout}")
    return ";".join(parts) + ";"


def _connection_attempts():
    database = os.environ.get("DB_NAME", "Chatbot_Ticketing_SYS")
    timeout = os.environ.get("DB_TIMEOUT", "5")

    # Try a strict local-only Shared Memory path first.
    for driver in _driver_candidates():
        if driver == "SQL Server":
            shared_memory = (
                f"DRIVER={{{driver}}};"
                f"SERVER={os.environ.get('DB_SERVER', 'localhost')};"
                f"DATABASE={database};"
                "Trusted_Connection=yes;"
                "Network=dbmslpcn;"
                f"Connection Timeout={timeout};"
            )
        else:
            shared_memory = (
                f"DRIVER={{{driver}}};"
                f"SERVER={os.environ.get('DB_SERVER', 'localhost')};"
                f"DATABASE={database};"
                "Trusted_Connection=yes;"
                "Network=dbmslpcn;"
                f"Encrypt={'yes' if _bool_setting('DB_ENCRYPT', False) else 'no'};"
                f"TrustServerCertificate={'yes' if _bool_setting('DB_TRUST_SERVER_CERTIFICATE', True) else 'no'};"
                f"Connection Timeout={timeout};"
            )
        yield driver, f"{os.environ.get('DB_SERVER', 'localhost')} [shared-memory]", shared_memory

    for driver in _driver_candidates():
        for server in _server_candidates():
            yield driver, server, _build_connection_string(driver, server)


def get_connection():
    errors = []

    for driver, server, connection_string in _connection_attempts():
        try:
            return pyodbc.connect(connection_string)
        except pyodbc.Error as error:
            errors.append(f"{driver} @ {server}: {error}")

    raise pyodbc.Error(
        "Unable to connect to SQL Server.\n"
        f"Servers tried: {', '.join(_server_candidates())}\n"
        f"Drivers tried: {', '.join(_driver_candidates()) or 'none'}\n"
        f"Database: {os.environ.get('DB_NAME', 'Chatbot_Ticketing_SYS')}\n"
        f"Details:\n" + "\n".join(errors)
    )


def test_connection():
    print("Testing SQL Server connection...")
    print(f"Configured server: {os.environ.get('DB_SERVER', 'localhost')}")
    print(f"Database: {os.environ.get('DB_NAME', 'Chatbot_Ticketing_SYS')}")
    print(f"Drivers available: {', '.join(_driver_candidates()) or 'none'}")
    print(f"Server candidates: {', '.join(_server_candidates())}")
    print(
        "Encrypt="
        + ("yes" if _bool_setting("DB_ENCRYPT", False) else "no")
        + " | TrustServerCertificate="
        + ("yes" if _bool_setting("DB_TRUST_SERVER_CERTIFICATE", True) else "no")
    )

    try:
        conn = None
        selected_driver = "unknown"
        selected_server = "unknown"

        for driver, server, connection_string in _connection_attempts():
            try:
                conn = pyodbc.connect(connection_string)
                selected_driver = driver
                selected_server = server
                break
            except pyodbc.Error:
                continue

        if conn is None:
            conn = get_connection()

        cursor = conn.cursor()
        cursor.execute("SELECT @@SERVERNAME, DB_NAME()")
        row = cursor.fetchone()
        print(
            "Database connection successful. "
            f"Driver: {selected_driver} | "
            f"Server: {selected_server} | "
            f"SQL Server: {row[0]} | Current DB: {row[1]}"
        )
        cursor.close()
        conn.close()
    except Exception as error:
        print(f"Database connection failed: {error}")
        print("Suggested checks:")
        print("1. Confirm the SQL Server instance accepts local trusted connections.")
        print("2. Open SSMS and compare the working server name to the candidates above.")
        print("3. If SSMS uses a named instance, put that exact value in DB_SERVER.")
        print("4. If Python still fails while SSMS works, the next step is SQL Server network protocol configuration.")


if __name__ == "__main__":
    test_connection()
