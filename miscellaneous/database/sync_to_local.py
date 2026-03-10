"""
sync_to_local.py
────────────────
Copies ALL tables from the remote SQL Server (DEBLNSVERP01)
into a local SQLite database at: database/xal_local1.db

Tables WITH a DATASET column are filtered to DATASET='INL'.
Tables WITHOUT a DATASET column are copied in full.

Run this script whenever you want a fresh offline copy:
    python database/sync_to_local.py
"""

import pyodbc
import sqlite3
import os
import sys
import time
from decimal import Decimal

# ── Config ────────────────────────────────────────────────────────────────────

SQL_SERVER_CONN = (
    "DRIVER={SQL Server};"
    "SERVER=DEBLNSVERP01;"
    "DATABASE=XALinl;"
    "UID=XAL_ODBC;"
    "PWD=XAL_ODBC;"
)

DATASET     = "INL"
BATCH_SIZE  = 5_000
DB_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xal_local1.db")

# ── Type mapping ──────────────────────────────────────────────────────────────

def clean_row(row) -> tuple:
    """Convert types that SQLite can't bind (e.g. Decimal → float)."""
    result = []
    for v in row:
        if isinstance(v, Decimal):
            result.append(float(v))
        else:
            result.append(v)
    return tuple(result)


def sql_to_sqlite_type(sql_type: str) -> str:
    t = sql_type.lower()
    if any(x in t for x in ("int", "bit")):
        return "INTEGER"
    if any(x in t for x in ("float", "real", "numeric", "decimal", "money")):
        return "REAL"
    return "TEXT"

# ── SQL Server helpers ────────────────────────────────────────────────────────

def get_all_tables(cursor) -> list[str]:
    cursor.execute("SELECT NAME FROM sys.tables ORDER BY NAME")
    return [row[0] for row in cursor.fetchall()]


def get_columns(cursor, table: str) -> list[tuple[str, str]]:
    """Returns [(col_name, sqlite_type), ...]"""
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, table)
    return [(row[0], sql_to_sqlite_type(row[1])) for row in cursor.fetchall()]


def column_exists(columns: list[tuple[str, str]], name: str) -> bool:
    return any(c[0].upper() == name.upper() for c in columns)


def get_remote_count(cursor, table: str, has_dataset: bool) -> int:
    if has_dataset:
        cursor.execute(f"SELECT COUNT(*) FROM [{table}] WHERE DATASET = ?", DATASET)
    else:
        cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
    return cursor.fetchone()[0]

# ── SQLite helpers ────────────────────────────────────────────────────────────

def create_sqlite_table(sqlite_conn, table: str, columns: list[tuple[str, str]]):
    col_defs = ", ".join(f'"{col}" {typ}' for col, typ in columns)
    sqlite_conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    sqlite_conn.execute(f'CREATE TABLE "{table}" ({col_defs})')
    sqlite_conn.commit()


def create_indexes(sqlite_conn, table: str, columns: list[tuple[str, str]]):
    important = {
        "DATASET", "ROWNUMBER", "ITEMNUMBER", "FATHERITEMNO",
        "CHILDITEMNO", "TXTID", "FATHERITEMNUM", "SCRIPTNUM", "LINENO_"
    }
    created = []
    for col, _ in columns:
        if col.upper() in important:
            sqlite_conn.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table}_{col}" ON "{table}" ("{col}")'
            )
            created.append(col)
    sqlite_conn.commit()
    if created:
        print(f"    Indexes: {', '.join(created)}")

# ── Table copy ────────────────────────────────────────────────────────────────

def copy_table(src_cursor, sqlite_conn, table: str, idx: int, total_tables: int):
    print(f"\n[{idx}/{total_tables}] {table}")

    columns     = get_columns(src_cursor, table)
    has_dataset = column_exists(columns, "DATASET")
    has_rownum  = column_exists(columns, "ROWNUMBER")
    order_col   = "ROWNUMBER" if has_rownum else "1"

    try:
        count = get_remote_count(src_cursor, table, has_dataset)
    except Exception:
        count = 0
    print(f"  Rows: {count:,}  |  DATASET filter: {has_dataset}")

    create_sqlite_table(sqlite_conn, table, columns)

    col_names    = [c for c, _ in columns]
    placeholders = ", ".join("?" * len(col_names))
    insert_sql   = f'INSERT INTO "{table}" VALUES ({placeholders})'

    offset  = 0
    copied  = 0
    start   = time.time()

    while True:
        try:
            if has_dataset:
                src_cursor.execute(f"""
                    SELECT {', '.join(f'[{c}]' for c in col_names)}
                    FROM [{table}]
                    WHERE DATASET = ?
                    ORDER BY {order_col}
                    OFFSET {offset} ROWS FETCH NEXT {BATCH_SIZE} ROWS ONLY
                """, DATASET)
            else:
                src_cursor.execute(f"""
                    SELECT {', '.join(f'[{c}]' for c in col_names)}
                    FROM [{table}]
                    ORDER BY {order_col}
                    OFFSET {offset} ROWS FETCH NEXT {BATCH_SIZE} ROWS ONLY
                """)
        except Exception as e:
            print(f"  FETCH ERROR: {e}")
            break

        rows = src_cursor.fetchall()
        if not rows:
            break

        sqlite_conn.executemany(insert_sql, [clean_row(r) for r in rows])
        sqlite_conn.commit()

        copied  += len(rows)
        elapsed  = time.time() - start
        pct      = (copied / count * 100) if count else 100
        rate     = copied / elapsed if elapsed > 0 else 0
        print(f"  {copied:>8,} / {count:,}  ({pct:5.1f}%)  {rate:.0f} rows/s", end="\r")

        offset += BATCH_SIZE
        if len(rows) < BATCH_SIZE:
            break

    elapsed = time.time() - start
    print(f"  {copied:>8,} rows  — {elapsed:.1f}s          ")
    create_indexes(sqlite_conn, table, columns)
    return copied

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  BOM_APP — Full Local DB Sync")
    print(f"  Target: {DB_PATH}")
    print("=" * 60)

    # Connect SQL Server
    print("\nConnecting to SQL Server...", end=" ", flush=True)
    try:
        src_conn   = pyodbc.connect(SQL_SERVER_CONN, timeout=10)
        src_cursor = src_conn.cursor()
        print("OK")
    except Exception as e:
        print(f"FAILED\n  {e}")
        sys.exit(1)

    # Get all tables
    tables = get_all_tables(src_cursor)
    print(f"Tables found: {len(tables)}")

    # Open SQLite (fresh)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Removed existing db file — starting fresh.")

    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_conn.execute("PRAGMA journal_mode = WAL")
    sqlite_conn.execute("PRAGMA synchronous  = NORMAL")
    sqlite_conn.execute("PRAGMA cache_size   = -64000")  # 64 MB

    total_start  = time.time()
    failed       = []

    for i, table in enumerate(tables, 1):
        try:
            copy_table(src_cursor, sqlite_conn, table, i, len(tables))
        except Exception as e:
            print(f"  ERROR on {table}: {e}")
            failed.append((table, str(e)))

    src_conn.close()
    sqlite_conn.close()

    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    elapsed = time.time() - total_start

    print(f"\n{'='*60}")
    print(f"  Sync complete in {elapsed:.1f}s")
    print(f"  DB size: {db_size:.1f} MB  |  Location: {DB_PATH}")
    if failed:
        print(f"\n  Failed tables ({len(failed)}):")
        for t, err in failed:
            print(f"    {t}: {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
