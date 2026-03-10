"""
STEP 7 — Auto-Document the Database
Goal: Run all discovery queries and write results to db_map.txt
Tells you: a complete snapshot of the database structure saved to a file
           so you can reference it while building the GUI.
"""

import os
from db_connection import get_connection

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), 'db_map.txt')
DATASET     = 'INL'


def write(f, text=''):
    print(text)
    f.write(text + '\n')


def section(f, title):
    write(f)
    write(f, '=' * 70)
    write(f, f'  {title}')
    write(f, '=' * 70)


def run():
    conn   = get_connection()
    cursor = conn.cursor()

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:

        write(f, 'DATABASE MAP — XALinl')
        write(f, f'Server : DEBLNSVERP01')
        write(f, f'Dataset: {DATASET}')
        write(f)

        # --- All tables + row counts ---
        section(f, 'ALL TABLES (sorted by row count)')
        cursor.execute("""
            SELECT t.NAME AS TableName, p.rows AS [RowCount]
            FROM sys.tables t
            JOIN sys.partitions p ON t.object_id = p.object_id
            WHERE p.index_id IN (0, 1)
            ORDER BY p.rows DESC
        """)
        for row in cursor.fetchall():
            write(f, f"  {row[0]:<40} {row[1]:>12,}")

        # --- Prefix groups ---
        section(f, 'TABLE PREFIX GROUPS')
        cursor.execute("""
            SELECT LEFT(TABLE_NAME, 4) AS Prefix, COUNT(*) AS TableCount
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            GROUP BY LEFT(TABLE_NAME, 4)
            ORDER BY TableCount DESC
        """)
        for row in cursor.fetchall():
            write(f, f"  {row.Prefix:<10}  {row.TableCount} tables")

        # --- Columns for each table ---
        section(f, 'COLUMN DETAILS PER TABLE')
        cursor.execute("""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = [r.TABLE_NAME for r in cursor.fetchall()]

        for table in tables:
            write(f, f"\n  [{table}]")
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """, (table,))
            cols = cursor.fetchall()
            for col in cols:
                max_len = f"({col.CHARACTER_MAXIMUM_LENGTH})" if col.CHARACTER_MAXIMUM_LENGTH else ''
                nullable = 'NULL' if col.IS_NULLABLE == 'YES' else 'NOT NULL'
                write(f, f"    {col.COLUMN_NAME:<35} {col.DATA_TYPE}{max_len:<20} {nullable}")

        # --- Dataset distribution ---
        section(f, 'DATASET DISTRIBUTION (key tables)')
        for table in ['STOCKTABLE', 'STOCKBILLMAT', 'TEXTS', 'B407SBM_INL']:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ? AND COLUMN_NAME = 'DATASET'
            """, (table,))
            if cursor.fetchone()[0]:
                cursor.execute(f"SELECT DATASET, COUNT(*) AS Rows FROM {table} GROUP BY DATASET ORDER BY Rows DESC")
                write(f, f"\n  {table}:")
                for row in cursor.fetchall():
                    write(f, f"    DATASET={row.DATASET}  rows={row.Rows:,}")

        write(f)
        write(f, f'Output saved to: {OUTPUT_FILE}')

    conn.close()
    print(f"\nDone. Full map written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
