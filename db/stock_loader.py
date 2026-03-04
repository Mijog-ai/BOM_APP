from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection

# Columns returned by StockSearchLoader — in display order
STOCK_COLUMNS = [
    'ItemNo', 'ItemName', 'FullName',
    'ItemGroup', 'ItemType',
    'CostPrice', 'SalesPrice',
    'StockUnit', 'MinLevel', 'MaxLevel',
    'DeliveryTime', 'Buyer', 'Supplier',
    'Blocked', 'ABCCode', 'NetWeight',
    'LastChanged',
]

# Human-readable headers matching STOCK_COLUMNS order
STOCK_HEADERS = [
    'Item No', 'Item Name', 'Full Name (TXT1)',
    'Item Group', 'Item Type',
    'Cost Price', 'Sales Price',
    'Stock Unit', 'Min Level', 'Max Level',
    'Del. Time', 'Buyer', 'Supplier',
    'Blocked', 'ABC', 'Net Weight',
    'Last Changed',
]


class StockParamLoader(QThread):
    """
    Loads distinct ITEMGROUP and ITEMTYPE values for the filter dropdowns.
    Emits params_ready(groups: list[str], types: list[str]).
    """
    params_ready = pyqtSignal(list, list)   # groups, types
    error        = pyqtSignal(str)

    def __init__(self, dataset: str = 'INL'):
        super().__init__()
        self.dataset = dataset

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT ITEMGROUP
                FROM XALinl.dbo.STOCKTABLE
                WHERE DATASET = ? AND ITEMGROUP IS NOT NULL AND ITEMGROUP != ''
                ORDER BY ITEMGROUP
            """, (self.dataset,))
            groups = [str(r[0]).strip() for r in cursor.fetchall()]

            cursor.execute("""
                SELECT DISTINCT ITEMTYPE
                FROM XALinl.dbo.STOCKTABLE
                WHERE DATASET = ? AND ITEMTYPE IS NOT NULL AND ITEMTYPE != ''
                ORDER BY ITEMTYPE
            """, (self.dataset,))
            types = [str(r[0]).strip() for r in cursor.fetchall()]

            conn.close()
            self.params_ready.emit(groups, types)

        except Exception as e:
            self.error.emit(str(e))


class StockSearchLoader(QThread):
    """
    Searches STOCKTABLE joined with TEXTS.
    Filters: free-text (ItemNo OR ItemName OR TXT1), ItemGroup, ItemType, Blocked.
    Returns up to `limit` rows, ordered by ITEMNUMBER.
    Emits data_ready(rows: list[dict]).
    """
    data_ready = pyqtSignal(list)   # list[dict] keyed by STOCK_COLUMNS
    error      = pyqtSignal(str)

    def __init__(self, dataset: str = 'INL', search: str = '',
                 itemgroup: str = '', itemtype: str = '',
                 blocked: str = '', limit: int = 300):
        super().__init__()
        self.dataset   = dataset
        self.search    = search.strip()
        self.itemgroup = itemgroup.strip()
        self.itemtype  = itemtype.strip()
        self.blocked   = blocked.strip()
        self.limit     = limit

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            # Build WHERE clauses dynamically
            conditions = ["st.DATASET = ?"]
            params     = [self.dataset]

            # Free-text: match ItemNo OR ItemName OR TXT1
            if self.search:
                like = f'%{self.search}%'
                conditions.append(
                    "(st.ITEMNUMBER LIKE ? OR st.ITEMNAME LIKE ? OR tx.TXT1 LIKE ?)"
                )
                params += [like, like, like]

            if self.itemgroup:
                conditions.append("st.ITEMGROUP = ?")
                params.append(self.itemgroup)

            if self.itemtype:
                conditions.append("st.ITEMTYPE = ?")
                params.append(self.itemtype)

            if self.blocked == 'Blocked':
                conditions.append("st.BLOCKED = 1")
            elif self.blocked == 'Active':
                conditions.append("(st.BLOCKED = 0 OR st.BLOCKED IS NULL)")

            where = " AND ".join(conditions)

            cursor.execute(f"""
                SELECT TOP {self.limit}
                    st.ITEMNUMBER       AS ItemNo,
                    st.ITEMNAME         AS ItemName,
                    tx.TXT1             AS FullName,
                    st.ITEMGROUP        AS ItemGroup,
                    st.ITEMTYPE         AS ItemType,
                    st.COSTPRICE        AS CostPrice,
                    st.SALESPRICE       AS SalesPrice,
                    st.STOCKUNIT        AS StockUnit,
                    st.MINSTOCKLEVEL    AS MinLevel,
                    st.MAXSTOCKLEVEL    AS MaxLevel,
                    st.DELIVERYTIME     AS DeliveryTime,
                    st.BUYER            AS Buyer,
                    st.PRIMARYSUPPLIER  AS Supplier,
                    st.BLOCKED          AS Blocked,
                    st.ABCCODE          AS ABCCode,
                    st.NETWEIGHT        AS NetWeight,
                    st.LASTCHANGED      AS LastChanged
                FROM XALinl.dbo.STOCKTABLE st
                LEFT JOIN XALinl.dbo.TEXTS tx
                    ON  tx.DATASET = st.DATASET
                    AND tx.TXTID   = st.ITEMNUMBER
                WHERE {where}
                ORDER BY st.ITEMNUMBER
            """, params)

            columns = [col[0] for col in cursor.description]
            rows    = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
            self.data_ready.emit(rows)

        except Exception as e:
            self.error.emit(str(e))
