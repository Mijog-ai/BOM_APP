from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection


class PartsCollectorLoader(QThread):
    """
    Given a list of father item numbers, recursively collects ALL parts
    across all their BOMs.  Deduplicates by CHILDITEMNO — each part
    appears only once regardless of how many BOMs contain it.

    Emits data_ready with a list of dicts (one per unique part).
    Emits progress with (current_count, message) during collection.
    """

    data_ready = pyqtSignal(list)
    progress   = pyqtSignal(int, str)
    error      = pyqtSignal(str)

    def __init__(self, father_items: list[str], dataset: str = 'INL'):
        super().__init__()
        self.father_items = father_items
        self.dataset = dataset

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            seen_items = set()
            all_parts  = []
            queue      = list(self.father_items)
            processed_fathers = set()

            while queue:
                father = queue.pop(0)
                if father in processed_fathers:
                    continue
                processed_fathers.add(father)

                self.progress.emit(
                    len(all_parts),
                    f"Loading BOM for {father}  ({len(all_parts)} unique parts so far)…"
                )

                cursor.execute("""
                    SELECT
                        sbm.CHILDITEMNO          AS ItemNo,
                        sbm.QTYTURNOVR           AS Qty,
                        sbm.POSITION             AS Position,
                        sbm.FATHERITEMNO         AS FatherItemNo,
                        st.ITEMNAME              AS Description,
                        st.ITEMTYPE              AS Artikelart,
                        st.STOCKLOC              AS StockLoc,
                        tx.TXT1                  AS FullName,
                        b.SCRIPTNUM              AS ScriptNum,
                        COALESCE(ss.Bestand, 0)  AS Bestand
                    FROM XALinl.dbo.STOCKBILLMAT sbm
                    INNER JOIN XALinl.dbo.STOCKTABLE st
                        ON  st.DATASET    = sbm.DATASET
                        AND st.ITEMNUMBER = sbm.CHILDITEMNO
                    LEFT JOIN XALinl.dbo.TEXTS tx
                        ON  tx.DATASET = sbm.DATASET
                        AND tx.TXTID   = sbm.CHILDITEMNO
                    LEFT JOIN XALinl.dbo.B407SBM_INL b
                        ON  b.DATASET        = sbm.DATASET
                        AND b.LINENO_        = sbm.LINENO_
                        AND b.FATHERITEMNUM  = sbm.FATHERITEMNO
                    LEFT JOIN (
                        SELECT DATASET, ITEMNUMBER,
                               SUM(ENTEREDQTY - DRAWN + RECEIVED) AS Bestand
                        FROM XALinl.dbo.STOCKSUM
                        GROUP BY DATASET, ITEMNUMBER
                    ) ss
                        ON  ss.DATASET    = sbm.DATASET
                        AND ss.ITEMNUMBER = sbm.CHILDITEMNO
                    WHERE sbm.DATASET      = ?
                      AND sbm.FATHERITEMNO = ?
                    ORDER BY sbm.POSITION
                """, (self.dataset, father))

                for row in cursor.fetchall():
                    (item_no, qty, position, father_no, description,
                     artikelart, stock_loc, full_name, scriptnum, bestand) = row

                    item_no_str = str(item_no or '').strip()
                    has_bom = (artikelart == 1)

                    if has_bom and item_no_str not in processed_fathers:
                        queue.append(item_no_str)

                    if item_no_str not in seen_items:
                        seen_items.add(item_no_str)
                        all_parts.append({
                            'ItemNo'      : item_no_str,
                            'Description' : str(description or '').strip(),
                            'FullName'    : str(full_name or '').strip(),
                            'Qty'         : qty,
                            'StockLoc'    : str(stock_loc or '').strip(),
                            'Bestand'     : bestand,
                            'ScriptNum'   : str(scriptnum or '').strip(),
                            'FatherItemNo': str(father_no or '').strip(),
                            'HasBOM'      : has_bom,
                        })

            conn.close()
            self.data_ready.emit(all_parts)

        except Exception as e:
            self.error.emit(str(e))
