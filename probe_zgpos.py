"""
Probe script: find where 'Zg.-Pos.-Nr' (drawing position number) lives in the DB.
Run with:  python probe_zgpos.py
"""
import pyodbc

CONN_STRING = (
    'DRIVER={SQL Server};'
    'SERVER=DEBLNSVERP01;'
    'DATABASE=XALinl;'
    'UID=XAL_ODBC;'
    'PWD=XAL_ODBC'
)

conn = pyodbc.connect(CONN_STRING, timeout=10)
cur  = conn.cursor()

# ── 1. Full STOCKBILLMAT column dump ────────────────────────────────────────
print("=" * 60)
print("STOCKBILLMAT — all columns (sample row)")
print("=" * 60)
cur.execute("SELECT TOP 1 * FROM XALinl.dbo.STOCKBILLMAT WHERE DATASET='INL'")
cols = [d[0] for d in cur.description]
row  = cur.fetchone()
for c, v in zip(cols, row):
    print(f"  {c:<35} = {v!r}")

# ── 2. STOCKTABLE DRAWFORMAT + all SPECNAMxx ────────────────────────────────
print()
print("=" * 60)
print("STOCKTABLE — DRAWFORMAT + SPECNAMxx  (5 rows with data)")
print("=" * 60)
cur.execute("""
    SELECT TOP 5
        ITEMNUMBER, ITEMNAME, DRAWFORMAT,
        SPECNAM1,  SPECNAM2,  SPECNAM3,  SPECNAM4,  SPECNAM5,
        SPECNAM6,  SPECNAM7,  SPECNAM8,  SPECNAM9,  SPECNAM10,
        SPECNAM11, SPECNAM12, SPECNAM13, SPECNAM14, SPECNAM15,
        SPECNAM16, SPECNAM17
    FROM XALinl.dbo.STOCKTABLE
    WHERE DATASET='INL'
      AND (
        LTRIM(RTRIM(SPECNAM9))  <> '' OR
        LTRIM(RTRIM(SPECNAM10)) <> '' OR
        LTRIM(RTRIM(SPECNAM11)) <> '' OR
        LTRIM(RTRIM(SPECNAM16)) <> '' OR
        LTRIM(RTRIM(DRAWFORMAT))<> ''
      )
""")
cols = [d[0] for d in cur.description]
for row in cur.fetchall():
    print("  " + "  |  ".join(
        f"{c}={v!r}" for c, v in zip(cols, row)
        if v is not None and str(v).strip() not in ('', '0')
    ))

# ── 3. B397STOCK_INL — full column dump ──────────────────────────────────────
print()
print("=" * 60)
print("B397STOCK_INL — all columns (sample row)")
print("=" * 60)
cur.execute("SELECT TOP 1 * FROM XALinl.dbo.B397STOCK_INL WHERE DATASET='INL'")
cols = [d[0] for d in cur.description]
row  = cur.fetchone()
for c, v in zip(cols, row):
    print(f"  {c:<35} = {v!r}")

# ── 4. Scan ALL tables for column names containing ZG, ZEICH, DRAWNO ─────────
print()
print("=" * 60)
print("ALL columns in ALL tables matching: ZG, ZEICH, DRAWNO, DRAWNR, POSNO, ZGPOS")
print("=" * 60)
cur.execute("""
    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE (
        COLUMN_NAME LIKE '%ZG%'   OR
        COLUMN_NAME LIKE '%ZEICH%' OR
        COLUMN_NAME LIKE '%DRAWNO%' OR
        COLUMN_NAME LIKE '%DRAWNR%' OR
        COLUMN_NAME LIKE '%POSNO%'  OR
        COLUMN_NAME LIKE '%ZGPOS%'
    )
    ORDER BY TABLE_NAME, COLUMN_NAME
""")
for row in cur.fetchall():
    print(f"  {row[0]:<35} {row[1]:<30} {row[2]}({row[3]})")

conn.close()
print()
print("Done.")
