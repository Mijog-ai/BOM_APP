"""
STEP 2 — Prefix Groups
Goal: Group tables by their first 4 characters to reveal ERP modules.
Tells you: STOCK = inventory, CUST = customers, GL = general ledger, etc.
"""

from db_connection import get_connection


def run():
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            LEFT(TABLE_NAME, 4)  AS Prefix,
            COUNT(*)             AS TableCount
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        GROUP BY LEFT(TABLE_NAME, 4)
        ORDER BY TableCount DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'Prefix':<10} {'TableCount':>12}")
    print("-" * 24)
    for row in rows:
        print(f"{row.Prefix:<10} {row.TableCount:>12}")

    print(f"\nTotal prefixes found: {len(rows)}")

    # Also list full table names per prefix for the top 5 prefixes
    top_prefixes = [row.Prefix for row in rows[:5]]
    for prefix in top_prefixes:
        print(f"\n--- Tables starting with '{prefix}' ---")
        cursor.execute("""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME LIKE ?
            ORDER BY TABLE_NAME
        """, (prefix + '%',))
        for r in cursor.fetchall():
            print(f"  {r.TABLE_NAME}")

    conn.close()


if __name__ == "__main__":
    run()
