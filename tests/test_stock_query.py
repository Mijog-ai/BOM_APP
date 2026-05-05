"""
Stock query test — items starting with 79%, ENT%, NA%
======================================================
Queries STOCKTABLE joined with B397STOCK_INL and STOCKSUM
to retrieve article details with stock levels.

Run
---
    python tests/test_stock_query.py
or from the project root:
    .venv\\Scripts\\python.exe tests/test_stock_query.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection

DATASET = 'INL'

QUERY = """
SELECT
    st.ITEMGROUP       AS [Artikelgruppe],
    st.ITEMNUMBER      AS [Artikelnummer],
    st.ITEMNAME        AS [Bezeichnung_1],
    st.ITEMNAME2UK     AS [Bezeichnung_2],
    st.ITEMNAME3UK     AS [Bezeichnung_3],
    st.STOCKLOC        AS [Lagerort],
    st.SPECNAM16       AS [MUC_Zchngnr.],
    st.ALTITEMNO       AS [Ersatzartikel],
    CASE
        WHEN st.USEALTITEMNO = 0 THEN 'Nie'
        WHEN st.USEALTITEMNO = 1 THEN 'Lager leer'
        WHEN st.USEALTITEMNO = 2 THEN 'Jedes Mal'
    END               AS [Ersatz benutzen!],
    b.PAINTIDX         AS [Index],
    st.DRAWFORMAT      AS [Format],
    COALESCE(SUM(ss.ENTEREDQTY - ss.DRAWN + ss.RECEIVED), 0) AS [Bestand]
FROM XALinl.dbo.STOCKTABLE      st
JOIN XALinl.dbo.B397STOCK_INL   b
  ON  b.DATASET    = st.DATASET
  AND b.ITEMNUMBER = st.ITEMNUMBER
LEFT JOIN XALinl.dbo.STOCKSUM   ss
  ON  ss.DATASET    = st.DATASET
  AND ss.ITEMNUMBER = st.ITEMNUMBER
WHERE
    st.DATASET = ?
    AND (
         st.ITEMNUMBER LIKE '79%'
      OR st.ITEMNUMBER LIKE 'ENT%'
      OR st.ITEMNUMBER LIKE 'NA%'
    )
GROUP BY
    st.ITEMGROUP, st.ITEMNUMBER, st.ITEMNAME, st.ITEMNAME2UK, st.ITEMNAME3UK,
    st.STOCKLOC, st.SPECNAM16, st.ALTITEMNO, st.USEALTITEMNO, b.PAINTIDX, st.DRAWFORMAT
ORDER BY
    st.ITEMNAME
"""

COLUMNS = [
    'Artikelgruppe',
    'Artikelnummer',
    'Bezeichnung_1',
    'Bezeichnung_2',
    'Bezeichnung_3',
    'Lagerort',
    'MUC_Zchngnr.',
    'Ersatzartikel',
    'Ersatz benutzen!',
    'Index',
    'Format',
    'Bestand',
]

SEP = '─' * 90


def run():
    conn = get_connection()
    cur = conn.cursor()

    print(SEP)
    print('  Stock Query — Items: 79% / ENT% / NA%')
    print(SEP)

    cur.execute(QUERY, (DATASET,))
    rows = cur.fetchall()

    print(f'  Total rows returned: {len(rows)}')
    print(SEP)

    col_widths = [max(len(c), 12) for c in COLUMNS]

    header = ' | '.join(c.ljust(w) for c, w in zip(COLUMNS, col_widths))
    print(header)
    print('-+-'.join('-' * w for w in col_widths))

    for row in rows:
        line = ' | '.join(str(val if val is not None else '').ljust(w) for val, w in zip(row, col_widths))
        print(line)

    conn.close()
    print()
    print(SEP)
    print(f'  Done. {len(rows)} row(s) displayed.')
    print(SEP)


if __name__ == '__main__':
    run()
