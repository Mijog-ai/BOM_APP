# BOM_APP — XAL ERP Database Explorer

## Project Goal
A PyQt6 desktop application to explore and visualize the XAL ERP database,
with a primary focus on Bill of Materials (BOM) hierarchies.

---

## Environment

| Item | Value |
|---|---|
| Server | DEBLNSVERP01 |
| Database | XALinl |
| Credentials | UID=XAL_ODBC / PWD=XAL_ODBC |
| Driver | SQL Server (ODBC) |
| Python | 3.x (.venv) |
| Key package | pyodbc 5.3.0 |
| SQL Server version | Pre-2017 (STRING_AGG not available — use FOR XML PATH) |

---

## Datasets (Companies) in XALinl

| Dataset | Rows (STOCKTABLE) | Notes |
|---|---|---|
| INL | 60,078 | Main company — always filter to this |
| KON | 80 | Tiny secondary company |

**Always filter `WHERE DATASET = 'INL'`** unless specifically exploring KON.

---

## Database Reference

**Every table in XALinl has these 3 standard columns first:**
```
DATASET       varchar(3)   NOT NULL   -- company key ('INL', 'KON')
ROWNUMBER     int          NOT NULL   -- internal row ID
LASTCHANGED   datetime     NOT NULL   -- last update timestamp
```

**Top tables by row count (the active business data):**
```
MRPIIPRIP          7,324,010   -- MRP production orders
STOCKTRANS         6,220,997   -- Stock transactions (movements)
H_COS_TO_XAL       5,597,350   -- History: cost
H_GUE_TO_XAL       4,067,349   -- History: something (external transfer)
NOTES              4,735,418   -- Free-text notes
MRPTRANS           2,956,787   -- MRP transactions
LEDTRANS           1,631,000   -- Ledger transactions (finance)
STOCKBILLMAT         369,637   -- BOM lines  ← CORE for this app
B407SBM_INL          227,152   -- BOM sequence/position data ← CORE
STOCKTABLE            60,158   -- Item master ← CORE
TEXTS                 26,488   -- Item descriptions ← CORE
```

**ERP Module Groups (table prefixes):**
```
DELE   -- Deletion logs (30 tables)
MRP    -- Manufacturing Resource Planning
STOCK  -- Inventory & BOM
LED    -- Ledger / Finance
CRED   -- Creditors (Vendors / Accounts Payable)
DEB    -- Debtors (Customers / Accounts Receivable)
SALES  -- Sales orders
PURCH  -- Purchase orders
B      -- Custom/extended XAL tables (many)
H_     -- History tables (large, read-only archive)
```

**Core BOM tables — column detail:**

`STOCKTABLE` — Item Master
```
ITEMGROUP     varchar(10)   item category
ITEMNUMBER    varchar(20)   PRIMARY KEY for items
ITEMNAME      varchar(40)   short description
ITEMTYPE      ...           type code
ITEMSTATUS    ...           active/inactive
... + many more fields
```

`STOCKBILLMAT` — BOM Lines (parent → child relationships)
```
FATHERITEMNO  varchar(20)   parent item number
LINENO_       numeric       line sequence
FATHERVARIANT varchar(10)   variant of parent
CHILDITEMNO   varchar(20)   child item number
BILLTYPE      ...           type of BOM line
QTYTURNOVR    numeric       quantity required
POSITION      ...           position in BOM
```

`TEXTS` — Item Descriptions
```
TXTID          varchar(30)   matches STOCKTABLE.ITEMNUMBER
LANGUAGE_CODE  int           language (0 = default)
TXT1           varchar(...)  full text description
```

`B407SBM_INL` — BOM Sequence (XAL custom)
```
SCRIPTNUM      -- position/sequence number
FATHERITEMNUM  -- links to STOCKBILLMAT.FATHERITEMNO
LINENO_        -- links to STOCKBILLMAT.LINENO_
```

**The working BOM JOIN (tested):**
```sql
SELECT
    B407SBM_INL.SCRIPTNUM        AS 'Pos.',
    STOCKBILLMAT.CHILDITEMNO     AS 'Item No.',
    STOCKBILLMAT.BILLTYPE        AS 'Billtype',
    STOCKTABLE.ITEMNAME          AS 'Description',
    TEXTS.TXT1                   AS 'Name',
    STOCKBILLMAT.QTYTURNOVR      AS 'Qty'
FROM XALinl.dbo.B407SBM_INL,
     XALinl.dbo.STOCKBILLMAT,
     XALinl.dbo.STOCKTABLE,
     XALinl.dbo.STOCKTABLE  STOCKTABLE_1,
     XALinl.dbo.TEXTS,
     XALinl.dbo.TEXTS        TEXTS_1
WHERE B407SBM_INL.DATASET         = STOCKBILLMAT.DATASET
  AND STOCKBILLMAT.LINENO_        = B407SBM_INL.LINENO_
  AND STOCKBILLMAT.FATHERITEMNO   = B407SBM_INL.FATHERITEMNUM
  AND STOCKTABLE.DATASET          = STOCKBILLMAT.DATASET
  AND STOCKBILLMAT.CHILDITEMNO    = STOCKTABLE.ITEMNUMBER
  AND TEXTS.DATASET               = STOCKTABLE.DATASET
  AND STOCKTABLE.ITEMNUMBER       = TEXTS.TXTID
  AND TEXTS.DATASET               = STOCKTABLE_1.DATASET
  AND STOCKBILLMAT.FATHERITEMNO   = STOCKTABLE_1.ITEMNUMBER
  AND TEXTS_1.DATASET             = TEXTS.DATASET
  AND STOCKTABLE_1.ITEMNUMBER     = TEXTS_1.TXTID
  AND STOCKBILLMAT.DATASET        = 'INL'
  AND STOCKBILLMAT.FATHERITEMNO LIKE ?
ORDER BY STOCKBILLMAT.POSITION
```

**No enforced FK constraints** — XAL uses logical joins only (common in older ERP).

---

## Implementation Notes

### SQL Server Compatibility (Pre-2017)
- `STRING_AGG` → NOT available. Use `STUFF + FOR XML PATH`
- `OFFSET/FETCH` → Available since SQL Server 2012, should work
- Window functions (`ROW_NUMBER`, `RANK`) → available
- `TRY_CAST` → available since 2012

### XAL-Specific Quirks
- Every table: `DATASET + ROWNUMBER` forms the composite key
- `LASTCHANGED` on every table — useful for "recently modified" filters
- No enforced foreign keys — all joins are logical
- Two companies: `INL` (main, 60K items) and `KON` (tiny, 80 items)
- `B`-prefix tables are XAL customizations, often INL-specific views
- `H_` prefix tables are history/archive — very large, treat as read-only

### Performance Rules
- **Never** `SELECT *` without `TOP N` or `OFFSET/FETCH` on large tables
- `MRPIIPRIP` (7.3M rows) and `STOCKTRANS` (6.2M) need extra caution
- Always include `WHERE DATASET = 'INL'` to halve search space
- Index columns: `DATASET`, `ROWNUMBER`, `ITEMNUMBER`, `FATHERITEMNO`

### PyQt6 Threading Rule
- **Never** run pyodbc queries on the main thread
- Always use `QThread` + `pyqtSignal` for all DB calls
- Pattern: Worker thread emits signal → main thread slot updates UI

### Outstanding TODOs
- Move credentials out of code into a config file

---

## File Reference

| File | Purpose |
|---|---|
| `app.py` | Entry point — QApplication + MainWindow |
| `db/connection.py` | DatabaseConnection class — pyodbc wrapper |
| `db/schema_loader.py` | QThread — fetches table list + row counts |
| `db/table_loader.py` | QThread — fetches paginated table data |
| `db/bom_loader.py` | QThread — BOM JOIN query + recursive exporter |
| `db/search_loader.py` | QThread — parses TXT1 into search parameters |
| `db/stock_loader.py` | QThread — stock search filters + query |
| `ui/main_window.py` | MainWindow — tab orchestration, schema, CSV export |
| `ui/bom_panel.py` | Tab 2 — lazy BOM tree + JSON export |
| `ui/search_panel.py` | Tab 3 — cascading Family→Size→Type filter |
| `ui/stock_panel.py` | Tab 4 — inventory search + detail + BOM link |
| `tests/db_map.txt` | Complete column map of all tables |
| `Test_setup_data/phase1_results.txt` | Full Phase 1 DB discovery output |
| `Test_setup_data/db_map.txt` | DB map (moved from tests/) |
