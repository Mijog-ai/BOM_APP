from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection


class BOMLoader(QThread):
    """
    Loads one level of BOM children for a given FATHERITEMNO.

    BILLTYPE == 1  →  the child itself has a BOM  (expandable node)
    BILLTYPE != 1  →  the child is a leaf          (no further BOM)

    Emits data_ready with a list of dicts, one per child item.
    Each dict contains both child AND father info (father info is the same
    on every row — used to label the parent tree node).
    """

    data_ready = pyqtSignal(list)   # list of row dicts
    error      = pyqtSignal(str)

    def __init__(self, item_no: str, dataset: str = 'INL'):
        super().__init__()
        self.item_no = item_no
        self.dataset = dataset

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    STOCKBILLMAT.POSITION            AS Position,
                    STOCKBILLMAT.CHILDITEMNO         AS ItemNo,
                    STOCKBILLMAT.QTYTURNOVR          AS Qty,
                    STOCKTABLE.ITEMTYPE              AS Artikelart,
                    STOCKTABLE.ITEMNAME              AS Description,
                    TEXTS.TXT1                       AS FullName,
                    STOCKTABLE_1.ITEMNUMBER          AS FatherItemNo,
                    STOCKTABLE_1.ITEMNAME            AS FatherDescription,
                    TEXTS_1.TXT1                     AS FatherFullName,
                    B407SBM_INL.SCRIPTNUM            AS ScriptNum
                FROM XALinl.dbo.STOCKBILLMAT STOCKBILLMAT
                INNER JOIN XALinl.dbo.STOCKTABLE STOCKTABLE
                    ON  STOCKTABLE.DATASET       = STOCKBILLMAT.DATASET
                    AND STOCKTABLE.ITEMNUMBER    = STOCKBILLMAT.CHILDITEMNO
                LEFT  JOIN XALinl.dbo.TEXTS TEXTS
                    ON  TEXTS.DATASET            = STOCKBILLMAT.DATASET
                    AND TEXTS.TXTID              = STOCKTABLE.ITEMNUMBER
                LEFT  JOIN XALinl.dbo.STOCKTABLE STOCKTABLE_1
                    ON  STOCKTABLE_1.DATASET     = STOCKBILLMAT.DATASET
                    AND STOCKTABLE_1.ITEMNUMBER  = STOCKBILLMAT.FATHERITEMNO
                LEFT  JOIN XALinl.dbo.TEXTS TEXTS_1
                    ON  TEXTS_1.DATASET          = STOCKBILLMAT.DATASET
                    AND TEXTS_1.TXTID            = STOCKBILLMAT.FATHERITEMNO
                LEFT  JOIN XALinl.dbo.B407SBM_INL B407SBM_INL
                    ON  B407SBM_INL.DATASET      = STOCKBILLMAT.DATASET
                    AND B407SBM_INL.LINENO_      = STOCKBILLMAT.LINENO_
                    AND B407SBM_INL.FATHERITEMNUM = STOCKBILLMAT.FATHERITEMNO
                WHERE STOCKBILLMAT.DATASET      = ?
                  AND STOCKBILLMAT.FATHERITEMNO = ?
                ORDER BY STOCKBILLMAT.POSITION
            """, (self.dataset, self.item_no))

            columns = [col[0] for col in cursor.description]
            rows    = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()

            self.data_ready.emit(rows)

        except Exception as e:
            self.error.emit(str(e))
