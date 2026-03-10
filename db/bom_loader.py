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
            """, (self.dataset, self.item_no))

            columns = [col[0] for col in cursor.description]
            rows    = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()

            self.data_ready.emit(rows)

        except Exception as e:
            self.error.emit(str(e))
