import decimal
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection


class BOMExporter(QThread):
    """
    Recursively walks the full BOM tree for a root item number using a single
    DB connection and builds a nested dict ready for JSON serialisation.

    Circular reference protection: each branch carries a 'visited' frozenset
    of item numbers already seen on the path from root → current node.
    If an item_no appears again it is flagged with "circular_ref": true
    instead of expanding infinitely.

    Emitted signals:
        progress(str)      — status messages while traversing
        export_ready(dict) — the complete nested structure when done
        error(str)         — any exception message
    """

    progress     = pyqtSignal(str)
    export_ready = pyqtSignal(dict)
    error        = pyqtSignal(str)

    def __init__(self, item_no: str, dataset: str = 'INL'):
        super().__init__()
        self.item_no     = item_no
        self.dataset     = dataset
        self._node_count = 0

    # ------------------------------------------------------------------ thread
    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            self.progress.emit(f"Starting export for  {self.item_no} ...")

            first_level = self._query_level(cursor, self.item_no)

            if first_level:
                root_desc     = _s(first_level[0].get('FatherDescription'))
                root_fullname = _s(first_level[0].get('FatherFullName'))
            else:
                root_desc = root_fullname = ''

            bom_tree = {
                'item_no':     self.item_no,
                'description': root_desc,
                'full_name':   root_fullname,
                'children':    self._build_children(
                    cursor, first_level,
                    visited=frozenset({self.item_no})
                ),
            }

            conn.close()
            self.progress.emit(
                f"Export complete — {self._node_count} item(s) in total."
            )

            output = {
                'metadata': {
                    'item_no':     self.item_no,
                    'dataset':     self.dataset,
                    'exported_at': datetime.now().isoformat(timespec='seconds'),
                    'total_items': self._node_count,
                },
                'bom': bom_tree,
            }
            self.export_ready.emit(output)

        except Exception as e:
            self.error.emit(str(e))

    # ------------------------------------------------------------------ helpers
    def _build_children(self, cursor, rows: list, visited: frozenset) -> list:
        children = []

        for row in rows:
            item_no = _s(row.get('ItemNo'))
            has_bom = (row.get('BillType') == 1)
            self._node_count += 1

            if self._node_count % 100 == 0:
                self.progress.emit(f"Traversed {self._node_count} items ...")

            node = {
                'pos':         _s(row.get('Pos')),
                'item_no':     item_no,
                'qty':         _f(row.get('Qty')),
                'billtype':    int(row.get('BillType') or 0),
                'has_bom':     has_bom,
                'description': _s(row.get('Description')),
                'full_name':   _s(row.get('FullName')),
                'children':    [],
            }

            if has_bom:
                if item_no in visited:
                    # Circular reference detected — do not recurse
                    node['circular_ref'] = True
                else:
                    sub_rows = self._query_level(cursor, item_no)
                    node['children'] = self._build_children(
                        cursor, sub_rows,
                        visited=visited | {item_no}   # new frozenset per branch
                    )

            children.append(node)

        return children

    def _query_level(self, cursor, item_no: str) -> list:
        """Return all direct children of item_no as a list of dicts."""
        cursor.execute("""
            SELECT
                B407SBM_INL.SCRIPTNUM           AS Pos,
                STOCKBILLMAT.CHILDITEMNO         AS ItemNo,
                STOCKBILLMAT.BILLTYPE            AS BillType,
                STOCKBILLMAT.QTYTURNOVR          AS Qty,
                STOCKBILLMAT.POSITION            AS Position,
                STOCKTABLE.ITEMNAME              AS Description,
                TEXTS.TXT1                       AS FullName,
                STOCKTABLE_1.ITEMNAME            AS FatherDescription,
                TEXTS_1.TXT1                     AS FatherFullName
            FROM XALinl.dbo.B407SBM_INL   B407SBM_INL,
                 XALinl.dbo.STOCKBILLMAT   STOCKBILLMAT,
                 XALinl.dbo.STOCKTABLE     STOCKTABLE,
                 XALinl.dbo.STOCKTABLE     STOCKTABLE_1,
                 XALinl.dbo.TEXTS          TEXTS,
                 XALinl.dbo.TEXTS          TEXTS_1
            WHERE B407SBM_INL.DATASET        = STOCKBILLMAT.DATASET
              AND STOCKBILLMAT.LINENO_       = B407SBM_INL.LINENO_
              AND STOCKBILLMAT.FATHERITEMNO  = B407SBM_INL.FATHERITEMNUM
              AND STOCKTABLE.DATASET         = STOCKBILLMAT.DATASET
              AND STOCKBILLMAT.CHILDITEMNO   = STOCKTABLE.ITEMNUMBER
              AND TEXTS.DATASET              = STOCKTABLE.DATASET
              AND STOCKTABLE.ITEMNUMBER      = TEXTS.TXTID
              AND TEXTS.DATASET              = STOCKTABLE_1.DATASET
              AND STOCKBILLMAT.FATHERITEMNO  = STOCKTABLE_1.ITEMNUMBER
              AND TEXTS_1.DATASET            = TEXTS.DATASET
              AND STOCKTABLE_1.ITEMNUMBER    = TEXTS_1.TXTID
              AND STOCKBILLMAT.DATASET       = ?
              AND STOCKBILLMAT.FATHERITEMNO  = ?
            ORDER BY STOCKBILLMAT.POSITION
        """, (self.dataset, item_no))

        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ------------------------------------------------------------------ type helpers
def _s(val) -> str:
    """Safe string conversion — turns None into empty string."""
    return str(val).strip() if val is not None else ''


def _f(val) -> float:
    """Safe float conversion — handles Decimal, None, empty."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
