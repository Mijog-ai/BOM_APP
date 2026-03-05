from PyQt6.QtCore import QThread, pyqtSignal
from db.connection import get_connection, IS_SQLITE

# Order matters — more specific prefixes must come before shorter ones
MODULE_PREFIXES = [
    ('MRPII',  'Manufacturing (MRP)'),
    ('MRPC',   'Manufacturing (MRP)'),
    ('MRPP',   'Manufacturing (MRP)'),
    ('MRPR',   'Manufacturing (MRP)'),
    ('MRPT',   'Manufacturing (MRP)'),
    ('MRP',    'Manufacturing (MRP)'),
    ('STOCK',  'Stock & BOM'),
    ('LED',    'Finance / Ledger'),
    ('CRED',   'Creditors'),
    ('DEB',    'Debtors'),
    ('SALE',   'Sales'),
    ('PURCH',  'Purchasing'),
    ('NOTE',   'Notes'),
    ('ADDR',   'Address'),
    ('ZIP',    'Address'),
    ('SPEC',   'Specifications'),
    ('BATCH',  'Batch'),
    ('PRIC',   'Pricing'),
    ('CAL',    'Calendar'),
    ('INTRA',  'Intrastat'),
    ('YEAR',   'Year Lists'),
    ('XML',    'XML Config'),
    ('XALT',   'XAL System'),
    ('XALD',   'XAL System'),
    ('NUM',    'Numbering'),
    ('PARAM',  'Parameters'),
    ('ACCOUNT','Accounts'),
    ('ACCT',   'Accounts'),
    ('H_',     'History'),
    ('DELE',   'Deleted Records'),
    ('B',      'Custom Tables'),
]


def get_module(table_name: str) -> str:
    upper = table_name.upper()
    for prefix, module in MODULE_PREFIXES:
        if upper.startswith(prefix):
            return module
    return 'Other'


class SchemaLoader(QThread):
    """Runs on a background thread. Emits schema_ready with all tables grouped by module."""

    schema_ready = pyqtSignal(dict)   # {module_name: [(table_name, row_count), ...]}
    error        = pyqtSignal(str)

    def run(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()

            if IS_SQLITE:
                cursor.execute(
                    "SELECT name, 0 FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            else:
                cursor.execute("""
                    SELECT t.NAME AS TableName, p.rows AS [RowCount]
                    FROM sys.tables t
                    JOIN sys.partitions p ON t.object_id = p.object_id
                    WHERE p.index_id IN (0, 1)
                    ORDER BY t.NAME
                """)
            rows = cursor.fetchall()
            conn.close()

            schema = {}
            for row in rows:
                module = get_module(row[0])
                schema.setdefault(module, []).append((row[0], row[1]))

            # Sort tables alphabetically within each module
            for module in schema:
                schema[module].sort(key=lambda x: x[0])

            self.schema_ready.emit(schema)

        except Exception as e:
            self.error.emit(str(e))
