"""
STEP 5 — Sample Raw Data
Goal: Preview first 10 rows of each key table (filtered to DATASET='INL').
Tells you: what real data looks like, which columns are populated vs NULL.
"""

from db_connection import get_connection

KEY_TABLES = [
    'STOCKTABLE',
    'STOCKBILLMAT',
    'TEXTS',
    'B407SBM_INL',
]

SAMPLE_SIZE = 10
DATASET     = 'INL'


def sample_table(cursor, table_name):
    # Check if DATASET column exists
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? AND COLUMN_NAME = 'DATASET'
    """, (table_name,))
    has_dataset = cursor.fetchone()[0]

    if has_dataset:
        cursor.execute(f"SELECT TOP {SAMPLE_SIZE} * FROM {table_name} WHERE DATASET = ?", (DATASET,))
    else:
        cursor.execute(f"SELECT TOP {SAMPLE_SIZE} * FROM {table_name}")

    columns = [col[0] for col in cursor.description]
    rows    = cursor.fetchall()

    print(f"\n{'='*70}")
    print(f"  TABLE: {table_name}  (showing up to {SAMPLE_SIZE} rows)")
    print(f"{'='*70}")

    if not rows:
        print("  No rows returned.")
        return

    # Print each row as key: value pairs for readability
    for i, row in enumerate(rows, 1):
        print(f"\n  --- Row {i} ---")
        for col, val in zip(columns, row):
            display_val = str(val).strip() if val is not None else 'NULL'
            # Truncate very long values
            if len(display_val) > 60:
                display_val = display_val[:57] + '...'
            print(f"    {col:<30}: {display_val}")


def run():
    conn = get_connection()
    cursor = conn.cursor()

    for table in KEY_TABLES:
        sample_table(cursor, table)

    conn.close()


if __name__ == "__main__":
    run()
