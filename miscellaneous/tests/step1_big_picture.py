"""
STEP 1 — Big Picture
Goal: Find all tables and their row counts, sorted largest first.
Tells you: which tables are the core business tables vs empty/unused.
"""

from db_connection import get_connection


def run():
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            t.NAME        AS TableName,
            p.rows        AS [RowCount]
        FROM sys.tables t
        JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0, 1)
        ORDER BY p.rows DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'TableName':<40} {'RowCount':>12}")
    print("-" * 54)
    for row in rows:
        print(f"{row.TableName:<40} {row[1]:>12,}")

    print(f"\nTotal tables found: {len(rows)}")
    conn.close()


if __name__ == "__main__":
    run()
