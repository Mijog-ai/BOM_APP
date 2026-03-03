"""
STEP 6 — Foreign Key Relationships
Goal: Find all FK constraints in the database.
Tells you: how tables are officially linked. If nothing is returned,
           XAL uses logical (unenforced) joins — which is common in older ERP.
"""

from db_connection import get_connection


def find_enforced_fks(cursor):
    print("\n=== ENFORCED FOREIGN KEYS (sys.foreign_keys) ===")

    cursor.execute("""
        SELECT
            fk.name                AS FK_Name,
            tp.name                AS ParentTable,
            cp.name                AS ParentColumn,
            tr.name                AS ReferencedTable,
            cr.name                AS ReferencedColumn
        FROM sys.foreign_keys fk
        JOIN sys.tables            tp  ON fk.parent_object_id     = tp.object_id
        JOIN sys.tables            tr  ON fk.referenced_object_id = tr.object_id
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        JOIN sys.columns           cp  ON fkc.parent_object_id     = cp.object_id
                                      AND fkc.parent_column_id     = cp.column_id
        JOIN sys.columns           cr  ON fkc.referenced_object_id = cr.object_id
                                      AND fkc.referenced_column_id = cr.column_id
        ORDER BY tp.name, tr.name
    """)

    rows = cursor.fetchall()

    if not rows:
        print("  No enforced FK constraints found.")
        print("  -> XAL likely uses logical (unenforced) joins. See step6b below.")
        return

    print(f"\n  {'ParentTable':<25} {'ParentCol':<25} {'ReferencedTable':<25} {'ReferencedCol':<25}")
    print(f"  {'-'*100}")
    for row in rows:
        print(f"  {row.ParentTable:<25} {row.ParentColumn:<25} {row.ReferencedTable:<25} {row.ReferencedColumn:<25}")

    print(f"\n  Total FK relationships: {len(rows)}")


def find_logical_joins(cursor):
    """
    Since XAL may not enforce FKs, find LOGICAL relationships by looking
    for column names that appear in multiple tables (common join keys).
    """
    print("\n=== LOGICAL RELATIONSHIPS (shared column names across tables) ===")
    print("  (Columns named identically in 2+ tables — likely join keys)\n")

    # STRING_AGG is SQL Server 2017+; use FOR XML PATH for older versions
    cursor.execute("""
        SELECT
            c.COLUMN_NAME,
            COUNT(DISTINCT c.TABLE_NAME) AS [TableCount],
            STUFF((
                SELECT ', ' + c2.TABLE_NAME
                FROM INFORMATION_SCHEMA.COLUMNS c2
                WHERE c2.COLUMN_NAME = c.COLUMN_NAME
                FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'),
            1, 2, '') AS Tables
        FROM INFORMATION_SCHEMA.COLUMNS c
        GROUP BY c.COLUMN_NAME
        HAVING COUNT(DISTINCT c.TABLE_NAME) >= 2
        ORDER BY [TableCount] DESC, c.COLUMN_NAME
    """)

    rows = cursor.fetchall()

    print(f"  {'ColumnName':<30} {'UsedIn':>8}  {'Tables'}")
    print(f"  {'-'*90}")
    for row in rows:
        tables_val = row[2] or ''
        tables_short = tables_val if len(tables_val) < 60 else tables_val[:57] + '...'
        print(f"  {row[0]:<30} {row[1]:>8}  {tables_short}")


def run():
    conn = get_connection()
    cursor = conn.cursor()

    find_enforced_fks(cursor)
    find_logical_joins(cursor)

    conn.close()


if __name__ == "__main__":
    run()
