"""
Article inspection test — 7959743.00
=====================================
Queries every relevant table for this article number and prints
all column names + values in a readable format.

Tables covered
--------------
  1. STOCKTABLE        — item master (full row)
  2. B397STOCK_INL     — INL-specific item extension (full row)
  3. TEXTS             — all text rows for this TXTID
  4. STOCKBILLMAT      — BOM lines where this item is the FATHER
  5. STOCKBILLMAT      — BOM lines where this item is a CHILD
  6. B407SBM_INL       — BOM sequence / script entries for this item

Run
---
    python tests/test_article_7959743.py
or from the project root:
    .venv\\Scripts\\python.exe tests/test_article_7959743.py
"""

import sys
import os

# ── allow imports from project root ─────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection

ITEM_NO = '7959743.00'
DATASET = 'INL'

SEP  = '─' * 72
SEP2 = '═' * 72


def print_section(title: str):
    print()
    print(SEP2)
    print(f'  {title}')
    print(SEP2)


def print_row(cols, row, indent: int = 2):
    """Print one DB row as column = value pairs."""
    pad = ' ' * indent
    max_col = max(len(c) for c in cols)
    for col, val in zip(cols, row):
        print(f'{pad}{col:<{max_col}}  =  {val!r}')


def print_rows(cols, rows, label='row'):
    if not rows:
        print('  (no rows found)')
        return
    for idx, row in enumerate(rows, start=1):
        if len(rows) > 1:
            print(f'  {SEP}')
            print(f'  [{label} {idx} of {len(rows)}]')
        print_row(cols, row)


def run():
    conn = get_connection()
    cur  = conn.cursor()

    # ── 1. STOCKTABLE ────────────────────────────────────────────────────────
    print_section(f'1. STOCKTABLE  —  ITEMNUMBER = {ITEM_NO!r}')
    cur.execute(
        'SELECT * FROM XALinl.dbo.STOCKTABLE WHERE DATASET=? AND ITEMNUMBER=?',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    print_rows(cols, cur.fetchall())

    # ── 2. B397STOCK_INL ────────────────────────────────────────────────────
    print_section(f'2. B397STOCK_INL  —  ITEMNUMBER = {ITEM_NO!r}')
    cur.execute(
        'SELECT * FROM XALinl.dbo.B397STOCK_INL WHERE DATASET=? AND ITEMNUMBER=?',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    print_rows(cols, cur.fetchall())

    # ── 3. TEXTS ─────────────────────────────────────────────────────────────
    print_section(f'3. TEXTS  —  TXTID = {ITEM_NO!r}')
    cur.execute(
        'SELECT * FROM XALinl.dbo.TEXTS WHERE DATASET=? AND TXTID=?',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    print_rows(cols, cur.fetchall(), label='language row')

    # ── 4. STOCKBILLMAT — as FATHER ─────────────────────────────────────────
    print_section(f'4. STOCKBILLMAT  —  FATHERITEMNO = {ITEM_NO!r}  (this item IS the BOM parent)')
    cur.execute(
        '''SELECT * FROM XALinl.dbo.STOCKBILLMAT
           WHERE DATASET=? AND FATHERITEMNO=?
           ORDER BY POSITION''',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f'  ({len(rows)} BOM child line(s) found)')
    print_rows(cols, rows, label='BOM line')

    # ── 5. STOCKBILLMAT — as CHILD ──────────────────────────────────────────
    print_section(f'5. STOCKBILLMAT  —  CHILDITEMNO = {ITEM_NO!r}  (this item APPEARS IN other BOMs)')
    cur.execute(
        '''SELECT * FROM XALinl.dbo.STOCKBILLMAT
           WHERE DATASET=? AND CHILDITEMNO=?
           ORDER BY FATHERITEMNO, POSITION''',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f'  ({len(rows)} parent BOM(s) contain this item)')
    print_rows(cols, rows, label='parent BOM line')

    # ── 6. B407SBM_INL ──────────────────────────────────────────────────────
    print_section(f'6. B407SBM_INL  —  FATHERITEMNUM = {ITEM_NO!r}')
    cur.execute(
        'SELECT * FROM XALinl.dbo.B407SBM_INL WHERE DATASET=? AND FATHERITEMNUM=?',
        (DATASET, ITEM_NO)
    )
    cols = [d[0] for d in cur.description]
    print_rows(cols, cur.fetchall(), label='script row')

    conn.close()
    print()
    print(SEP2)
    print('  Done.')
    print(SEP2)


if __name__ == '__main__':
    run()
