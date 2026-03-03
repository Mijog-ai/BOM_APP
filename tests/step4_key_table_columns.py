"""
STEP 4 — Key Table Column Inspector
Goal: Show all columns (name, type, nullable) for each known key table.
Tells you: what data each table holds, which columns are important.
"""

from db_connection import get_connection

KEY_TABLES = [
    'STOCKTABLE',
    'STOCKBILLMAT',
    'TEXTS',
    'B407SBM_INL',
]


def inspect_table(cursor, table_name):
    cursor.execute("""
        SELECT
            ORDINAL_POSITION  AS Pos,
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH AS MaxLen,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, (table_name,))

    rows = cursor.fetchall()

    if not rows:
        print(f"\n[{table_name}] — table not found or no columns")
        return

    print(f"\n{'='*60}")
    print(f"  TABLE: {table_name}  ({len(rows)} columns)")
    print(f"{'='*60}")
    print(f"  {'#':<4} {'ColumnName':<30} {'Type':<15} {'MaxLen':>7} {'Nullable'}")
    print(f"  {'-'*60}")
    for row in rows:
        max_len = str(row.MaxLen) if row.MaxLen else '-'
        print(f"  {row.Pos:<4} {row.COLUMN_NAME:<30} {row.DATA_TYPE:<15} {max_len:>7}  {row.IS_NULLABLE}")


def run():
    conn = get_connection()
    cursor = conn.cursor()

    for table in KEY_TABLES:
        inspect_table(cursor, table)

    conn.close()


if __name__ == "__main__":
    run()
