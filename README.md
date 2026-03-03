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

## Phase 1 — COMPLETED (Database Discovery)

### What was done
- All 7 discovery scripts are in `tests/`
- Full output saved to `phase1_results.txt`
- Full column-level DB map saved to `tests/db_map.txt`
- Runner script: `run_phase1.py`

### Key Database Findings

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

**The working JOIN (from main.py — already tested):**
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

## Phase 2 — PyQt6 GUI (TO BUILD)

### Overall Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  MENUBAR: File | View | Export                                   │
├───────────────┬─────────────────────────┬───────────────────────┤
│  LEFT PANEL   │   CENTER PANEL          │   RIGHT PANEL         │
│  QTreeWidget  │   QTableView            │   QScrollArea         │
│               │                         │                       │
│ 📁 XALinl     │  [Search]  [Dataset ▼]  │  Selected Row:        │
│  ├ STOCK      │                         │  ┌─────────────────┐  │
│  ├ MRP        │  Col1  Col2  Col3 ...   │  │ Field : Value   │  │
│  ├ SALES      │  ─────────────────────  │  │ Field : Value   │  │
│  ├ PURCH      │  val   val   val   ...  │  └─────────────────┘  │
│  ├ LED        │  val   val   val   ...  │                       │
│  └ ...        │                         │  [Copy Row]           │
│               │  [◀ Prev] 1 / N [Next ▶]│                       │
├───────────────┴─────────────────────────┴───────────────────────┤
│  STATUS BAR:  Connected │ STOCKTABLE │ 60,158 rows │ Page 1/121  │
└─────────────────────────────────────────────────────────────────┘
```

### PyQt6 Components

| Panel | Class | Notes |
|---|---|---|
| Window | `QMainWindow` | Main container |
| 3-panel split | `QSplitter` (horizontal) | Resizable panels |
| Left tree | `QTreeWidget` | Module → Table hierarchy |
| Center table | `QTableView` | Data grid |
| Table model | `QStandardItemModel` | Holds the data |
| Filter proxy | `QSortFilterProxyModel` | Client-side search |
| Search bar | `QLineEdit` | Filters proxy model |
| Dataset dropdown | `QComboBox` | Switch INL / KON |
| Pagination | `QPushButton` + `QLabel` | Prev/Next page |
| Right panel | `QFormLayout` in `QScrollArea` | Row detail view |
| Status bar | `QStatusBar` | Connection + counts |
| DB thread | `QThread` + `pyqtSignal` | Never block UI |
| Menu bar | `QMenuBar` | File/Export actions |

### Data Flow (CRITICAL — always use QThread)

```
User clicks table name in Tree
        │
        ▼
Emit signal → TableLoaderThread starts
  └── SQL: SELECT TOP 500 * FROM {table} WHERE DATASET = ?
  └── Uses OFFSET/FETCH NEXT for pagination
        │
        ▼
Thread emits results_ready(data, columns) signal
        │
        ▼
Main thread slot receives signal
  └── Populates QStandardItemModel
  └── QTableView auto-refreshes
  └── Status bar updates
```

### Pagination SQL (use this pattern)
```sql
SELECT * FROM {table}
WHERE DATASET = 'INL'
ORDER BY ROWNUMBER
OFFSET {page * page_size} ROWS
FETCH NEXT {page_size} ROWS ONLY
```
Use `page_size = 500`. Pre-query `COUNT(*)` once per table selection.

---

## Phase 3 — Suggested Class Structure

```
BOM_APP/
├── main.py                  (entry point — QApplication + MainWindow)
├── db/
│   ├── connection.py        (DatabaseConnection class — pyodbc wrapper)
│   ├── schema_loader.py     (QThread — fetches table list + row counts)
│   └── table_loader.py      (QThread — fetches paginated table data)
├── ui/
│   ├── main_window.py       (MainWindow(QMainWindow))
│   ├── tree_panel.py        (TableTreeWidget(QTreeWidget))
│   ├── data_panel.py        (DataTableView — QTableView + model + proxy)
│   ├── detail_panel.py      (RowDetailPanel — QScrollArea + QFormLayout)
│   └── status_bar.py        (AppStatusBar(QStatusBar))
├── tests/                   (Phase 1 discovery scripts — keep for reference)
└── phase1_results.txt       (Phase 1 output — reference)
```

### Class Responsibilities

**`DatabaseConnection`** (`db/connection.py`)
- Holds one `pyodbc` connection
- Methods: `connect()`, `disconnect()`, `is_alive()`, `reconnect()`
- Exposes connection string (read from config, not hardcoded)

**`SchemaLoader(QThread)`** (`db/schema_loader.py`)
- Signal: `schema_ready(dict)` — emits `{module: [table_name, ...]}`
- Runs on startup, queries INFORMATION_SCHEMA + sys.partitions
- Groups tables by prefix into modules

**`TableLoader(QThread)`** (`db/table_loader.py`)
- Signal: `data_ready(list[dict], list[str])` — rows + column names
- Signal: `count_ready(int)` — total row count
- Takes: table_name, dataset, page, page_size
- Runs paginated SELECT query

**`MainWindow(QMainWindow)`** (`ui/main_window.py`)
- Owns all panels via `QSplitter`
- Connects signals between tree → loader → table view
- Manages status bar updates

---

## Phase 4 — BOM-Specific Feature (the real purpose)

Once the generic table explorer works, add the BOM tree viewer:

### BOM Hierarchy View
- User types/searches an item number (e.g. `7956271.00`)
- App runs the working JOIN query from main.py
- Results show in a **tree structure** (not flat table):
  ```
  7956271.00 — Assembly XYZ
  ├── 1001.00  (Qty: 2)  — Bracket A
  ├── 1002.00  (Qty: 1)  — Motor Unit
  │    ├── 2001.00 (Qty: 4) — Bolt M8
  │    └── 2002.00 (Qty: 1) — Housing
  └── 1003.00  (Qty: 1)  — Cover Plate
  ```
- Use `QTreeWidget` with columns: Pos | Item No | Qty | Description
- "Drill down" button — click a child item to load ITS BOM

### Widget for BOM: `QTreeWidget` columns
```
Pos. | Item Number | Billtype | Description | Name | Qty
```

---

## Phase 5 — Features Build Order

1. DB connection class + config file (move credentials out of code)
2. Schema loader thread → populate left tree with modules/tables
3. Table viewer — click table → load 500 rows → display in QTableView
4. Search/filter bar using QSortFilterProxyModel
5. Pagination (Prev/Next page buttons)
6. Row detail panel (right side)
7. Dataset dropdown (INL / KON switcher)
8. Export to CSV
9. **BOM search tab** — item number input → BOM tree viewer
10. BOM drill-down (recursive child loading)

---

## Phase 6 — Important Implementation Notes

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

---

## File Reference

| File | Purpose |
|---|---|
| `main.py` | Original BOM query function (reference implementation) |
| `run_phase1.py` | Runs all discovery steps |
| `phase1_results.txt` | Full Phase 1 output |
| `tests/db_map.txt` | Complete column map of all tables |
| `tests/db_connection.py` | Shared pyodbc connection |
| `tests/step1_big_picture.py` | Table list + row counts |
| `tests/step2_prefix_groups.py` | Module grouping |
| `tests/step3_dataset_column.py` | Dataset distribution |
| `tests/step4_key_table_columns.py` | Column inspector |
| `tests/step5_sample_data.py` | Raw data sampler |
| `tests/step6_foreign_keys.py` | FK + logical join finder |
| `tests/step7_document.py` | DB map generator |
