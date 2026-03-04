from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFormLayout, QScrollArea, QFrame,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from db.stock_loader import (
    StockParamLoader, StockSearchLoader,
    STOCK_COLUMNS, STOCK_HEADERS,
)

_ANY = '— Any —'

# Columns shown in the RESULTS TABLE (subset of STOCK_COLUMNS for readability)
_TABLE_COLS = [
    'ItemNo', 'ItemName', 'FullName',
    'ItemGroup', 'ItemType',
    'CostPrice', 'SalesPrice',
    'StockUnit', 'Blocked',
]
_TABLE_HDRS = [
    'Item No', 'Item Name', 'Full Name',
    'Group', 'Type',
    'Cost Price', 'Sales Price',
    'Unit', 'Blocked',
]


class StockPanel(QWidget):
    """
    Tab 4 — Stocks

    Left  : search bar + filter dropdowns + results table (60 %)
    Right : item detail panel with all key fields  (40 %)

    The detail panel has an "Open BOM" button that loads the selected
    item into the BOM Tree tab (if the main window exposes it).
    """

    def __init__(self, bom_panel=None, parent=None):
        """
        bom_panel : reference to BOMPanel so "Open BOM" can load directly.
                    Pass None if not available yet; set later via set_bom_panel().
        """
        super().__init__(parent)
        self._bom_panel     = bom_panel
        self._param_loader  = None
        self._search_loader = None
        self._current_item  = None   # dict of selected row

        self._setup_ui()
        self._load_params()

    def set_bom_panel(self, bom_panel):
        self._bom_panel = bom_panel

    # ══════════════════════════════════════════════════════════════════
    # UI BUILD
    # ══════════════════════════════════════════════════════════════════
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Filter / search bar ────────────────────────────────────
        bar = QHBoxLayout()

        self._cb_dataset = QComboBox()
        self._cb_dataset.addItems(['INL', 'KON'])
        self._cb_dataset.setFixedWidth(70)

        self._txt_search = QLineEdit()
        self._txt_search.setPlaceholderText("Item No, Name or Full Name …")
        self._txt_search.setMinimumWidth(200)
        self._txt_search.returnPressed.connect(self._do_search)

        self._cb_group = QComboBox()
        self._cb_group.setMinimumWidth(110)
        self._cb_group.setToolTip("Filter by Item Group")

        self._cb_type = QComboBox()
        self._cb_type.setMinimumWidth(100)
        self._cb_type.setToolTip("Filter by Item Type")

        self._cb_blocked = QComboBox()
        self._cb_blocked.addItems([_ANY, 'Active', 'Blocked'])
        self._cb_blocked.setFixedWidth(90)
        self._cb_blocked.setToolTip("Show active, blocked, or all items")

        self._btn_search = QPushButton("Search")
        self._btn_search.setFixedWidth(90)
        self._btn_search.setEnabled(False)
        self._btn_search.clicked.connect(self._do_search)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self._clear)

        bar.addWidget(QLabel("Dataset:"))
        bar.addWidget(self._cb_dataset)
        bar.addSpacing(8)
        bar.addWidget(QLabel("Search:"))
        bar.addWidget(self._txt_search, 1)
        bar.addWidget(QLabel("Group:"))
        bar.addWidget(self._cb_group)
        bar.addWidget(QLabel("Type:"))
        bar.addWidget(self._cb_type)
        bar.addWidget(QLabel("Status:"))
        bar.addWidget(self._cb_blocked)
        bar.addSpacing(8)
        bar.addWidget(self._btn_search)
        bar.addWidget(self._btn_clear)
        root.addLayout(bar)

        # ── Status ─────────────────────────────────────────────────
        self._status = QLabel("Loading filter parameters …")
        root.addWidget(self._status)

        # ── Splitter: results table | detail panel ─────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── LEFT: results table ────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_TABLE_COLS))
        self._table.setHorizontalHeaderLabels(_TABLE_HDRS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch          # stretch Full Name col
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(0, 130)  # Item No
        self._table.setColumnWidth(1, 160)  # Item Name
        self._table.setColumnWidth(3, 80)   # Group
        self._table.setColumnWidth(4, 60)   # Type
        self._table.setColumnWidth(5, 80)   # Cost Price
        self._table.setColumnWidth(6, 80)   # Sales Price
        self._table.setColumnWidth(7, 55)   # Unit
        self._table.setColumnWidth(8, 55)   # Blocked
        self._table.currentItemChanged.connect(
            lambda curr, prev: self._on_row_selected(self._table.row(curr)) if curr else None
        )

        left_layout.addWidget(self._table)
        splitter.addWidget(left)

        # ── RIGHT: item detail panel ────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)

        right_layout.addWidget(QLabel("Item Detail:"))

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        form_widget = QWidget()
        self._form  = QFormLayout(form_widget)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setSpacing(6)
        scroll.setWidget(form_widget)
        right_layout.addWidget(scroll, 1)

        # "Open BOM" button
        self._btn_open_bom = QPushButton("Open BOM in BOM Tree tab")
        self._btn_open_bom.setEnabled(False)
        self._btn_open_bom.clicked.connect(self._open_bom)
        right_layout.addWidget(self._btn_open_bom)

        splitter.addWidget(right)
        splitter.setSizes([900, 500])
        root.addWidget(splitter, 1)

        # Dataset change reloads params
        self._cb_dataset.currentIndexChanged.connect(self._on_dataset_changed)

    # ══════════════════════════════════════════════════════════════════
    # PARAMETER LOADING (filter dropdowns)
    # ══════════════════════════════════════════════════════════════════
    def _load_params(self):
        dataset = self._cb_dataset.currentText()
        self._btn_search.setEnabled(False)
        self._param_loader = StockParamLoader(dataset)
        self._param_loader.params_ready.connect(self._on_params_ready)
        self._param_loader.error.connect(self._on_error)
        self._param_loader.start()

    def _on_params_ready(self, groups: list, types: list):
        self._cb_group.blockSignals(True)
        self._cb_group.clear()
        self._cb_group.addItem(_ANY, '')
        for g in groups:
            self._cb_group.addItem(g, g)
        self._cb_group.blockSignals(False)

        self._cb_type.blockSignals(True)
        self._cb_type.clear()
        self._cb_type.addItem(_ANY, '')
        for t in types:
            self._cb_type.addItem(t, t)
        self._cb_type.blockSignals(False)

        self._btn_search.setEnabled(True)
        self._status.setText(
            f"Ready — {len(groups)} item groups, {len(types)} item types loaded. "
            f"Enter a search term or select filters then click Search."
        )

    def _on_dataset_changed(self, _):
        self._table.setRowCount(0)
        self._clear_detail()
        self._status.setText("Reloading parameters …")
        self._load_params()

    # ══════════════════════════════════════════════════════════════════
    # SEARCH
    # ══════════════════════════════════════════════════════════════════
    def _do_search(self):
        search    = self._txt_search.text().strip()
        group     = self._cb_group.currentData() or ''
        itype     = self._cb_type.currentData()  or ''
        blocked   = self._cb_blocked.currentText()
        if blocked == _ANY:
            blocked = ''

        dataset = self._cb_dataset.currentText()

        self._table.setRowCount(0)
        self._clear_detail()
        self._status.setText("Searching …")
        self._btn_search.setEnabled(False)

        if self._search_loader and self._search_loader.isRunning():
            self._search_loader.quit()
            self._search_loader.wait()

        self._search_loader = StockSearchLoader(
            dataset=dataset,
            search=search,
            itemgroup=group,
            itemtype=itype,
            blocked=blocked,
            limit=300,
        )
        self._search_loader.data_ready.connect(self._on_search_ready)
        self._search_loader.error.connect(self._on_error)
        self._search_loader.start()

    def _on_search_ready(self, rows: list):
        self._btn_search.setEnabled(True)

        if not rows:
            self._status.setText("No items found matching your filters.")
            return

        # Store full rows for detail panel
        self._all_rows = rows

        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, col in enumerate(_TABLE_COLS):
                val  = row.get(col)
                text = ''
                if val is None:
                    text = ''
                elif col == 'Blocked':
                    text = 'Yes' if val else 'No'
                elif col in ('CostPrice', 'SalesPrice', 'NetWeight'):
                    try:
                        text = f"{float(val):.4f}"
                    except (TypeError, ValueError):
                        text = str(val)
                else:
                    text = str(val).strip()

                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r)  # store row index

                # Highlight blocked items in red
                if col == 'Blocked' and val:
                    item.setForeground(QColor('#C62828'))
                    for cc in range(len(_TABLE_COLS)):
                        pass   # set row colour below

                self._table.setItem(r, c, item)

            # Colour entire row red for blocked items
            if row.get('Blocked'):
                for c in range(len(_TABLE_COLS)):
                    cell = self._table.item(r, c)
                    if cell:
                        cell.setForeground(QColor('#C62828'))

        cap = " (showing first 300)" if len(rows) == 300 else ""
        self._status.setText(f"{len(rows)} item(s) found{cap} — click a row for details")

    # ══════════════════════════════════════════════════════════════════
    # ROW SELECTION → detail panel
    # ══════════════════════════════════════════════════════════════════
    def _on_row_selected(self, row: int):
        if row < 0 or not hasattr(self, '_all_rows'):
            return
        if row >= len(self._all_rows):
            return

        data = self._all_rows[row]
        self._current_item = data
        self._populate_detail(data)
        self._btn_open_bom.setEnabled(True)

    def _populate_detail(self, data: dict):
        self._clear_detail()

        # Define display order and labels for the detail form
        fields = [
            ('ItemNo',       'Item Number'),
            ('ItemName',     'Item Name (short)'),
            ('FullName',     'Full Name (TXT1)'),
            ('ItemGroup',    'Item Group'),
            ('ItemType',     'Item Type'),
            ('CostPrice',    'Cost Price'),
            ('SalesPrice',   'Sales Price'),
            ('StockUnit',    'Stock Unit'),
            ('MinLevel',     'Min Stock Level'),
            ('MaxLevel',     'Max Stock Level'),
            ('DeliveryTime', 'Delivery Time'),
            ('Buyer',        'Buyer'),
            ('Supplier',     'Primary Supplier'),
            ('Blocked',      'Blocked'),
            ('ABCCode',      'ABC Code'),
            ('NetWeight',    'Net Weight'),
            ('LastChanged',  'Last Changed'),
        ]

        bold = QFont()
        bold.setBold(True)

        for key, label in fields:
            val = data.get(key)
            if key == 'Blocked':
                display = 'Yes' if val else 'No'
            elif key in ('CostPrice', 'SalesPrice', 'NetWeight') and val is not None:
                try:
                    display = f"{float(val):.4f}"
                except (TypeError, ValueError):
                    display = str(val) if val is not None else '—'
            else:
                display = str(val).strip() if val is not None else '—'

            val_label = QLabel(display)
            val_label.setWordWrap(True)
            val_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            # Highlight item number and full name
            if key in ('ItemNo', 'FullName'):
                val_label.setFont(bold)

            # Red for blocked
            if key == 'Blocked' and val:
                val_label.setStyleSheet("color: #C62828; font-weight: bold;")

            lbl = QLabel(f"<b>{label}:</b>")
            self._form.addRow(lbl, val_label)

    def _clear_detail(self):
        while self._form.rowCount():
            self._form.removeRow(0)
        self._btn_open_bom.setEnabled(False)
        self._current_item = None

    # ══════════════════════════════════════════════════════════════════
    # OPEN BOM
    # ══════════════════════════════════════════════════════════════════
    def _open_bom(self):
        if not self._current_item:
            return
        item_no = str(self._current_item.get('ItemNo') or '').strip()
        if not item_no:
            return
        if self._bom_panel:
            self._bom_panel.load_item(item_no)

    # ══════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════
    def _clear(self):
        self._txt_search.clear()
        self._cb_group.setCurrentIndex(0)
        self._cb_type.setCurrentIndex(0)
        self._cb_blocked.setCurrentIndex(0)
        self._table.setRowCount(0)
        self._clear_detail()
        self._status.setText("Cleared.")

    def _on_error(self, msg: str):
        self._btn_search.setEnabled(True)
        self._status.setText(f"Error: {msg}")
