"""
STEP 3 — Dataset Column (XAL Multi-Company Check)
Goal: Find which DATASET values exist in the core tables.
Tells you: how many companies/datasets are in this XAL instance.
"""

from db_connection import get_connection

TABLES_TO_CHECK = [
    'STOCKTABLE',
    'STOCKBILLMAT',
    'TEXTS',
    'B407SBM_INL',
]


def check_dataset_in_table(cursor, table_name):
    # First check if DATASET column exists in this table
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? AND COLUMN_NAME = 'DATASET'
    """, (table_name,))
    has_dataset = cursor.fetchone()[0]

    if not has_dataset:
        print(f"\n[{table_name}] — no DATASET column")
        return

    cursor.execute(f"""
        SELECT DATASET, COUNT(*) AS Rows
        FROM {table_name}
        GROUP BY DATASET
        ORDER BY Rows DESC
    """)
    rows = cursor.fetchall()

    print(f"\n[{table_name}]")
    print(f"  {'DATASET':<15} {'Rows':>10}")
    print(f"  {'-'*27}")
    for row in rows:
        print(f"  {str(row.DATASET):<15} {row.Rows:>10,}")


def run():
    conn = get_connection()
    cursor = conn.cursor()

    for table in TABLES_TO_CHECK:
        check_dataset_in_table(cursor, table)

    conn.close()


if __name__ == "__main__":
    run()
