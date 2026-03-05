from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection, IS_SQLITE


class TableLoader(QThread):
    """Runs on a background thread. Loads paginated rows for a single table."""

    count_ready = pyqtSignal(int)         # total row count for the table
    data_ready  = pyqtSignal(list, list)  # (rows as list-of-lists, column names)
    error       = pyqtSignal(str)

    def __init__(self, table_name: str, dataset: str = 'INL',
                 page: int = 0, page_size: int = 500, load_count: bool = True):
        super().__init__()
        self.table_name  = table_name
        self.dataset     = dataset
        self.page        = page
        self.page_size   = page_size
        self.load_count  = load_count

    def _has_column(self, cursor, column: str) -> bool:
        if IS_SQLITE:
            cursor.execute(f"PRAGMA table_info({self.table_name})")
            return any(row[1] == column for row in cursor.fetchall())
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
            """, (self.table_name, column))
            return cursor.fetchone()[0] > 0

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            has_dataset   = self._has_column(cursor, 'DATASET')
            has_rownumber = self._has_column(cursor, 'ROWNUMBER')
            order_col     = 'ROWNUMBER' if has_rownumber else '(SELECT NULL)'

            # --- Row count (only on first page or forced) ---
            if self.load_count:
                if has_dataset:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {self.table_name} WHERE DATASET = ?",
                        (self.dataset,)
                    )
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                self.count_ready.emit(cursor.fetchone()[0])

            # --- Paginated data ---
            offset = self.page * self.page_size

            if IS_SQLITE:
                if has_dataset:
                    cursor.execute(f"""
                        SELECT * FROM {self.table_name}
                        WHERE DATASET = ?
                        ORDER BY {order_col}
                        LIMIT ? OFFSET ?
                    """, (self.dataset, self.page_size, offset))
                else:
                    cursor.execute(f"""
                        SELECT * FROM {self.table_name}
                        ORDER BY {order_col}
                        LIMIT ? OFFSET ?
                    """, (self.page_size, offset))
            else:
                if has_dataset:
                    cursor.execute(f"""
                        SELECT * FROM {self.table_name}
                        WHERE DATASET = ?
                        ORDER BY {order_col}
                        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                    """, (self.dataset, offset, self.page_size))
                else:
                    cursor.execute(f"""
                        SELECT * FROM {self.table_name}
                        ORDER BY {order_col}
                        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                    """, (offset, self.page_size))

            columns = [col[0] for col in cursor.description]
            rows    = [list(row) for row in cursor.fetchall()]

            conn.close()
            self.data_ready.emit(rows, columns)

        except Exception as e:
            self.error.emit(str(e))
