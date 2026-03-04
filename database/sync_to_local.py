"""
sync_to_local.py
────────────────
Copies the 4 core BOM tables from the remote SQL Server (DEBLNSVERP01)
into a local SQLite database at:  H:/Python_projects/BOM_APP/database/xal_local.db

Run this script whenever you want a fresh offline copy.
Usage:
    python database/sync_to_local.py

Tables copied (all filtered to DATASET='INL'):
    STOCKTABLE    ~60K rows   — item master
    STOCKBILLMAT  ~370K rows  — BOM parent→child lines
    TEXTS         ~26K rows   — item descriptions
    B407SBM_INL   ~227K rows  — BOM sequence/position data
"""

import pyodbc
import sqlite3
import os
import time

# ── Config ────────────────────────────────────────────────────────────────────

SQL_SERVER_CONN = (
    "DRIVER={SQL Server};"
    "SERVER=DEBLNSVERP01;"
    "DATABASE=XALinl;"
    "UID=XAL_ODBC;"
    "PWD=XAL_ODBC;"
)

DATASET = "INL"

DB_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "xal_local.db")

BATCH_SIZE = 5_000   # rows fetched + inserted per batch

# ── Tables to sync ────────────────────────────────────────────────────────────
# Each entry: (sql_server_table, order_by_column)
TABLES = [
    ("STOCKTABLE",   "ROWNUMBER"),
    ("STOCKBILLMAT", "ROWNUMBER"),
    ("TEXTS",        "ROWNUMBER"),
    ("B407SBM_INL",  "ROWNUMBER"),
]

# ── SQLite type mapping ───────────────────────────────────────────────────────

def sql_to_sqlite_type(sql_type: str) -> str:
    sql_type = sql_type.lower()
    if any(t in sql_type for t in ("int", "numeric", "decimal", "float", "real", "bit")):
        return "NUMERIC"
    if "datetime" in sql_type or "date" in sql_type:
        return "TEXT"
    return "TEXT"   # varchar, nvarchar, char, etc.


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_columns(cursor, table: str) -> list[tuple[str, str]]:
    """Return [(col_name, sqlite_type), ...] for a SQL Server table."""
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, table)
    return [(row[0], sql_to_sqlite_type(row[1])) for row in cursor.fetchall()]


def get_remote_count(cursor, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM XALinl.dbo.{table} WHERE DATASET = ?", DATASET)
    return cursor.fetchone()[0]


def create_sqlite_table(sqlite_conn, table: str, columns: list[tuple[str, str]]):
    """Drop-and-recreate the table in SQLite."""
    col_defs = ", ".join(f'"{col}" {typ}' for col, typ in columns)
    sqlite_conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    sqlite_conn.execute(f'CREATE TABLE "{table}" ({col_defs})')
    sqlite_conn.commit()


def create_indexes(sqlite_conn, table: str, columns: list[tuple[str, str]]):
    """Create indexes on commonly joined/filtered columns."""
    col_names = [c[0].upper() for c, _ in [(c, t) for c, t in columns]]

    important = {
        "DATASET", "ROWNUMBER", "ITEMNUMBER", "FATHERITEMNO",
        "CHILDITEMNO", "TXTID", "FATHERITEMNUM", "SCRIPTNUM", "LINENO_"
    }
    created = []
    for col, _ in columns:
        if col.upper() in important:
            idx_name = f"idx_{table}_{col}"
            sqlite_conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("{col}")'
            )
            created.append(col)
    sqlite_conn.commit()
    if created:
        print(f"    Indexes on: {', '.join(created)}")


def copy_table(src_cursor, sqlite_conn, table: str, order_col: str):
    print(f"\n{'─'*60}")
    print(f"  Table: {table}")

    columns = get_columns(src_cursor, table)
    total   = get_remote_count(src_cursor, table)
    print(f"  Rows to copy: {total:,}")

    create_sqlite_table(sqlite_conn, table, columns)

    col_names   = [c for c, _ in columns]
    placeholders = ", ".join("?" * len(col_names))
    insert_sql   = f'INSERT INTO "{table}" VALUES ({placeholders})'

    # Paginate with OFFSET / FETCH NEXT (works on SQL Server 2012+)
    offset   = 0
    copied   = 0
    start    = time.time()

    while True:
        src_cursor.execute(f"""
            SELECT {', '.join(col_names)}
            FROM XALinl.dbo.{table}
            WHERE DATASET = ?
            ORDER BY {order_col}
            OFFSET {offset} ROWS
            FETCH NEXT {BATCH_SIZE} ROWS ONLY
        """, DATASET)

        rows = src_cursor.fetchall()
        if not rows:
            break

        # Convert rows to plain tuples (pyodbc Row → tuple)
        sqlite_conn.executemany(insert_sql, [tuple(r) for r in rows])
        sqlite_conn.commit()

        copied += len(rows)
        elapsed = time.time() - start
        pct     = (copied / total * 100) if total else 100
        rate    = copied / elapsed if elapsed > 0 else 0
        print(f"    {copied:>7,} / {total:,}  ({pct:.1f}%)  — {rate:.0f} rows/s", end="\r")

        offset += BATCH_SIZE
        if len(rows) < BATCH_SIZE:
            break

    print(f"    {copied:>7,} / {total:,}  (100.0%)  — done in {time.time()-start:.1f}s")
    create_indexes(sqlite_conn, table, columns)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  BOM_APP — Local DB Sync")
    print(f"  Target: {DB_PATH}")
    print("=" * 60)

    print("\nConnecting to SQL Server...", end=" ")
    try:
        src_conn   = pyodbc.connect(SQL_SERVER_CONN, timeout=10)
        src_cursor = src_conn.cursor()
        print("OK")
    except Exception as e:
        print(f"FAILED\n  {e}")
        return

    sqlite_conn = sqlite3.connect(DB_PATH)
    # Performance settings for bulk inserts
    sqlite_conn.execute("PRAGMA journal_mode = WAL")
    sqlite_conn.execute("PRAGMA synchronous  = NORMAL")
    sqlite_conn.execute("PRAGMA cache_size   = -64000")   # 64 MB cache

    total_start = time.time()

    for table, order_col in TABLES:
        try:
            copy_table(src_cursor, sqlite_conn, table, order_col)
        except Exception as e:
            print(f"\n  ERROR copying {table}: {e}")

    src_conn.close()
    sqlite_conn.close()

    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    elapsed = time.time() - total_start

    print(f"\n{'='*60}")
    print(f"  Sync complete in {elapsed:.1f}s")
    print(f"  DB size: {db_size:.1f} MB")
    print(f"  Location: {DB_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
