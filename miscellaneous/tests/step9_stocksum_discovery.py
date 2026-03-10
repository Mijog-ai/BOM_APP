"""
STEP 9 — STOCKSUM / B397STOCK_INL Column Discovery
Goal: Understand the stock quantity tables so we can add
      live stock levels to the Stocks tab later.

Tables investigated:
  STOCKSUM      (69,472 rows)  — likely aggregated stock quantities
  B397STOCK_INL (60,209 rows)  — INL-specific stock extension
  STOCKLOCATIONS (731 rows)    — warehouse locations
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from db_connection import get_connection

DATASET    = 'INL'
SAMPLE_N   = 5

TABLES = [
    'STOCKSUM',
    'B397STOCK_INL',
    'STOCKLOCATIONS',
    'STOCKLEDGER',
]


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────
def get_columns(cursor, table):
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, (table,))
    return cursor.fetchall()


def sample_rows(cursor, table, dataset_col=True, n=SAMPLE_N):
    try:
        if dataset_col:
            cursor.execute(
                f"SELECT TOP {n} * FROM XALinl.dbo.{table} WHERE DATASET = ?",
                (DATASET,)
            )
        else:
            cursor.execute(f"SELECT TOP {n} * FROM XALinl.dbo.{table}")
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        return cols, rows
    except Exception as e:
        return [], [f"ERROR: {e}"]


def has_dataset_col(cursor, table):
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? AND COLUMN_NAME = 'DATASET'
    """, (table,))
    return cursor.fetchone()[0] > 0


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def run():
    conn   = get_connection()
    cursor = conn.cursor()

    for table in TABLES:
        print(f"\n{'='*70}")
        print(f"  TABLE: {table}")
        print(f"{'='*70}")

        # Columns
        cols_info = get_columns(cursor, table)
        if not cols_info:
            print(f"  !! Table not found in INFORMATION_SCHEMA")
            continue

        print(f"\n  COLUMNS ({len(cols_info)} total):")
        for col_name, dtype, maxlen in cols_info:
            maxlen_str = f"({maxlen})" if maxlen else ""
            print(f"    {col_name:<35} {dtype}{maxlen_str}")

        # Sample data
        has_ds = has_dataset_col(cursor, table)
        col_names, rows = sample_rows(cursor, table, dataset_col=has_ds)

        print(f"\n  SAMPLE ROWS (up to {SAMPLE_N}, DATASET={DATASET if has_ds else 'N/A'}):")
        if not rows:
            print("  No rows returned.")
        elif isinstance(rows[0], str):
            print(f"  {rows[0]}")
        else:
            # Print as key: value
            for i, row in enumerate(rows, 1):
                print(f"\n  --- Row {i} ---")
                for cname, val in zip(col_names, row):
                    display = str(val).strip() if val is not None else 'NULL'
                    if len(display) > 60:
                        display = display[:57] + '...'
                    print(f"    {cname:<35}: {display}")

    # ── Special: check if STOCKSUM links to STOCKTABLE ──
    print(f"\n{'='*70}")
    print("  EXTRA — Does STOCKSUM have ITEMNUMBER column?")
    print(f"{'='*70}")
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'STOCKSUM'
          AND COLUMN_NAME IN ('ITEMNUMBER','ITEMNO','ITEM_NO','STOCKID')
    """)
    matches = cursor.fetchall()
    if matches:
        print(f"  Found potential join key: {[m[0] for m in matches]}")
    else:
        print("  None of ITEMNUMBER/ITEMNO/ITEM_NO/STOCKID found in STOCKSUM")
        print("  → Check STOCKSUM columns above and identify the item key manually")

    conn.close()
    print("\n  Done.")


if __name__ == "__main__":
    run()
