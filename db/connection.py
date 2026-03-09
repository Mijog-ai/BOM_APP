import pyodbc

CONN_STRING = (
    'DRIVER={SQL Server};'
    'SERVER=DEBLNSVERP01;'
    'DATABASE=XALinl;'
    'UID=XAL_ODBC;'
    'PWD=XAL_ODBC'
)

def _can_connect():
    try:
        pyodbc.connect(CONN_STRING, timeout=3).close()
        return True
    except Exception:
        return False

_server_ok = _can_connect()
IS_SQLITE = not _server_ok

if _server_ok:
    def get_connection():
        return pyodbc.connect(CONN_STRING)
else:
    import sqlite3
    import os

    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database", "xal_local1.db")

    print(f"SQL Server unavailable — using local DB: {DB_PATH}")

    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn