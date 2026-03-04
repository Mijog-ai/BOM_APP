import re
from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection


def parse_txt1(txt1: str):
    """
    Parse a TXT1 description into (family, size, type_code).

    TXT1 structure:  <FAMILY>-<SIZE>  <TYPECODE>-<rest>
    e.g.  'V30D-095 RKN-1-0-02/LV*'  →  ('V30D', '095', 'RKN')
          'V30GL-160 R D1 F V 1/LR'  →  ('V30GL', '160', None)
          'Seal kit NBR ...'          →  (None, None, None)

    Returns (family, size, type_code) — any may be None.
    """
    if not txt1:
        return None, None, None

    parts = txt1.strip().split()
    if not parts:
        return None, None, None

    # First token must be  LETTERS-DIGITS  e.g.  V30D-095
    m = re.match(r'^([A-Z][A-Z0-9]*)-(\d+)', parts[0])
    if not m:
        return None, None, None

    family = m.group(1)   # V30D, V30GL, V30B, V30E …
    size   = m.group(2)   # 095, 140, 066 …

    # Second token leading uppercase letters → type code e.g. RKN, RKGN, RSN
    type_code = None
    if len(parts) >= 2:
        m2 = re.match(r'^([A-Z]{2,})', parts[1])
        if m2:
            type_code = m2.group(1)

    return family, size, type_code


class SearchParamLoader(QThread):
    """
    Fetches all distinct (SCRIPTNUM, FATHERITEMNUM, ITEMNAME, TXT1) rows
    from B407SBM_INL joined with STOCKTABLE + TEXTS, then parses each TXT1
    into (family, size, type_code) in Python.

    Emits data_ready with a list of dicts — one per unique father item.
    """

    data_ready = pyqtSignal(list)   # list[dict]
    error      = pyqtSignal(str)

    def __init__(self, dataset: str = 'INL'):
        super().__init__()
        self.dataset = dataset

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT
                    b.SCRIPTNUM,
                    b.FATHERITEMNUM,
                    st.ITEMNAME,
                    tx.TXT1
                FROM XALinl.dbo.B407SBM_INL b
                JOIN XALinl.dbo.STOCKTABLE  st
                    ON  st.DATASET    = b.DATASET
                    AND st.ITEMNUMBER = b.FATHERITEMNUM
                JOIN XALinl.dbo.TEXTS tx
                    ON  tx.DATASET = b.DATASET
                    AND tx.TXTID   = b.FATHERITEMNUM
                WHERE b.DATASET = ?
            """, (self.dataset,))

            scripts = []
            for row in cursor.fetchall():
                scriptnum, fatheritem, itemname, txt1 = row
                txt1_clean = str(txt1 or '').strip()
                family, size, type_code = parse_txt1(txt1_clean)
                scripts.append({
                    'scriptnum' : scriptnum,
                    'father'    : str(fatheritem or '').strip(),
                    'itemname'  : str(itemname   or '').strip(),
                    'txt1'      : txt1_clean,
                    'family'    : family,
                    'size'      : size,
                    'type_code' : type_code,
                })

            conn.close()
            self.data_ready.emit(scripts)

        except Exception as e:
            self.error.emit(str(e))
