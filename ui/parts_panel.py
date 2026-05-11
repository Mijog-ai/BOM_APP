import csv

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from db.search_loader    import SearchParamLoader
from db.parts_collector  import PartsCollectorLoader

_ANY = '— Any —'


class PartsPanel(QWidget):
    """
    Tab 3 — Parts Finder

    Inputs  : Dataset, Family, Size, Type  (same cascading filters as Compare BOM)
    Output  : flat table of ALL unique parts found across every matching BOM,
              recursively collected through the entire BOM hierarchy.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_scripts   = []
        self._param_loader  = None
        self._parts_loader  = None

        self._setup_ui()
        self._load_params()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        bar = QHBoxLayout()

        self._cb_dataset = QComboBox()
        self._cb_dataset.addItems(['INL', 'KON'])
        self._cb_dataset.setFixedWidth(70)
        self._cb_dataset.setToolTip("Dataset to search")

        self._cb_family = QComboBox()
        self._cb_family.setMinimumWidth(110)
        self._cb_family.setToolTip("Product family  e.g. V30D, V30E, V30GL")

        self._cb_size = QComboBox()
        self._cb_size.setMinimumWidth(90)
        self._cb_size.setToolTip("Size / displacement  e.g. 095, 140")

        self._cb_type = QComboBox()
        self._cb_type.setMinimumWidth(120)
        self._cb_type.setToolTip("Control type code  e.g. RKN, RKGN, RSN")

        self._btn_search = QPushButton("Search")
        self._btn_search.setFixedWidth(90)
        self._btn_search.setEnabled(False)

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.setFixedWidth(90)
        self._btn_export.setEnabled(False)
        self._btn_export.setToolTip("Export the current table to a CSV file")

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)

        self._chk_leaf_only = QCheckBox("Leaf parts only")
        self._chk_leaf_only.setChecked(False)
        self._chk_leaf_only.setToolTip(
            "Checked  → show only parts that have no sub-BOM (raw materials / purchased parts)\n"
            "Unchecked → show all parts including assemblies"
        )

        bar.addWidget(QLabel("Dataset:"))
        bar.addWidget(self._cb_dataset)
        bar.addSpacing(8)
        bar.addWidget(QLabel("Family:"))
        bar.addWidget(self._cb_family)
        bar.addWidget(QLabel("Size:"))
        bar.addWidget(self._cb_size)
        bar.addWidget(QLabel("Type:"))
        bar.addWidget(self._cb_type)
        bar.addSpacing(8)
        bar.addWidget(self._chk_leaf_only)
        bar.addSpacing(8)
        bar.addWidget(self._btn_search)
        bar.addWidget(self._btn_export)
        bar.addWidget(self._btn_clear)
        bar.addStretch()
        root.addLayout(bar)

        self._status = QLabel("Loading parameters from database …")
        root.addWidget(self._status)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            'Item No', 'Description', 'Full Name',
            'Stock Loc', 'Bestand', 'SCRIPTNUM', 'Found In BOM',
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSortingEnabled(True)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(1, 200)

        root.addWidget(self._table, 1)

        self._cb_dataset.currentIndexChanged.connect(self._on_dataset_changed)
        self._cb_family.currentIndexChanged.connect(self._on_family_changed)
        self._cb_size.currentIndexChanged.connect(self._on_size_changed)
        self._btn_search.clicked.connect(self._do_search)
        self._btn_export.clicked.connect(self._export_csv)
        self._btn_clear.clicked.connect(self._clear)

    # ── Parameter loading (reuses SearchParamLoader) ─────────────────
    def _load_params(self):
        dataset = self._cb_dataset.currentText()
        self._btn_search.setEnabled(False)
        self._param_loader = SearchParamLoader(dataset)
        self._param_loader.data_ready.connect(self._on_params_ready)
        self._param_loader.error.connect(self._on_error)
        self._param_loader.start()

    def _on_params_ready(self, scripts: list):
        self._all_scripts = scripts
        self._rebuild_family_combo()
        self._btn_search.setEnabled(True)
        parsed = sum(1 for d in scripts if d['family'])
        self._status.setText(
            f"Ready — {len(scripts)} scripts loaded  "
            f"({parsed} fully parsed).  Select filters and click Search."
        )

    # ── Cascading combos ─────────────────────────────────────────────
    def _rebuild_family_combo(self):
        families = sorted(set(
            d['family'] for d in self._all_scripts if d['family']
        ))
        self._cb_family.blockSignals(True)
        self._cb_family.clear()
        self._cb_family.addItem(_ANY, None)
        for f in families:
            self._cb_family.addItem(f, f)
        self._cb_family.blockSignals(False)
        self._rebuild_size_combo()

    def _rebuild_size_combo(self):
        family   = self._cb_family.currentData()
        filtered = self._all_scripts if not family else [
            d for d in self._all_scripts if d['family'] == family
        ]
        sizes = sorted(
            set(d['size'] for d in filtered if d['size']),
            key=lambda s: int(s) if s.isdigit() else 0,
        )
        self._cb_size.blockSignals(True)
        self._cb_size.clear()
        self._cb_size.addItem(_ANY, None)
        for s in sizes:
            self._cb_size.addItem(s, s)
        self._cb_size.blockSignals(False)
        self._rebuild_type_combo()

    def _rebuild_type_combo(self):
        family   = self._cb_family.currentData()
        size     = self._cb_size.currentData()
        filtered = self._all_scripts
        if family:
            filtered = [d for d in filtered if d['family'] == family]
        if size:
            filtered = [d for d in filtered if d['size'] == size]
        types = sorted(set(
            d['type_code'] for d in filtered if d['type_code']
        ))
        self._cb_type.blockSignals(True)
        self._cb_type.clear()
        self._cb_type.addItem(_ANY, None)
        for t in types:
            self._cb_type.addItem(t, t)
        self._cb_type.blockSignals(False)

    def _on_dataset_changed(self, _):
        self._all_scripts = []
        self._table.setRowCount(0)
        self._status.setText("Reloading parameters …")
        self._load_params()

    def _on_family_changed(self, _):
        self._rebuild_size_combo()

    def _on_size_changed(self, _):
        self._rebuild_type_combo()

    # ── Search ───────────────────────────────────────────────────────
    def _do_search(self):
        family = self._cb_family.currentData()
        size   = self._cb_size.currentData()
        tcode  = self._cb_type.currentData()

        results = self._all_scripts
        if family:
            results = [d for d in results if d['family'] == family]
        if size:
            results = [d for d in results if d['size'] == size]
        if tcode:
            results = [d for d in results if d['type_code'] == tcode]

        if not results:
            self._table.setRowCount(0)
            self._status.setText("No matching BOMs found.")
            return

        seen_fathers = set()
        father_items = []
        for d in results:
            if d['father'] not in seen_fathers:
                seen_fathers.add(d['father'])
                father_items.append(d['father'])

        self._btn_search.setEnabled(False)
        self._table.setRowCount(0)
        self._status.setText(
            f"Collecting parts from {len(father_items)} BOM(s) …"
        )

        dataset = self._cb_dataset.currentText()
        self._parts_loader = PartsCollectorLoader(father_items, dataset)
        self._parts_loader.data_ready.connect(self._on_parts_ready)
        self._parts_loader.progress.connect(self._on_progress)
        self._parts_loader.error.connect(self._on_error)
        self._parts_loader.start()

    def _on_progress(self, count: int, msg: str):
        self._status.setText(msg)

    def _on_parts_ready(self, parts: list):
        self._btn_search.setEnabled(True)
        self._btn_export.setEnabled(True)

        if self._chk_leaf_only.isChecked():
            parts = [p for p in parts if not p['HasBOM']]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(parts))

        for row_idx, part in enumerate(parts):
            item_no = QTableWidgetItem(part['ItemNo'])
            desc    = QTableWidgetItem(part['Description'])
            full    = QTableWidgetItem(part['FullName'])
            loc     = QTableWidgetItem(part['StockLoc'])
            script  = QTableWidgetItem(part['ScriptNum'])
            father  = QTableWidgetItem(part['FatherItemNo'])

            bestand_val = part['Bestand']
            bestand = QTableWidgetItem()
            bestand.setData(Qt.ItemDataRole.DisplayRole, float(bestand_val) if bestand_val else 0.0)

            if part['HasBOM']:
                for cell in (item_no, desc, full, loc, bestand, script, father):
                    cell.setForeground(QColor('#1565C0'))

            self._table.setItem(row_idx, 0, item_no)
            self._table.setItem(row_idx, 1, desc)
            self._table.setItem(row_idx, 2, full)
            self._table.setItem(row_idx, 3, loc)
            self._table.setItem(row_idx, 4, bestand)
            self._table.setItem(row_idx, 5, script)
            self._table.setItem(row_idx, 6, father)

        self._table.setSortingEnabled(True)

        total   = len(parts)
        leaf    = sum(1 for p in parts if not p['HasBOM'])
        assembly = total - leaf
        filter_tag = "leaf only" if self._chk_leaf_only.isChecked() else "all"
        self._status.setText(
            f"{total} unique parts found ({leaf} leaf + {assembly} assemblies)  "
            f"[{filter_tag}]"
        )

    # ── Export ────────────────────────────────────────────────────────
    def _export_csv(self):
        rows = self._table.rowCount()
        if rows == 0:
            self._status.setText("Nothing to export.")
            return

        parts = [self._cb_dataset.currentText()]
        family = self._cb_family.currentData()
        size   = self._cb_size.currentData()
        tcode  = self._cb_type.currentData()
        if family: parts.append(family)
        if size:   parts.append(size)
        if tcode:  parts.append(tcode)
        default_name = "_".join(parts) + "_parts.csv"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Parts to CSV", default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        cols = self._table.columnCount()
        headers = [
            self._table.horizontalHeaderItem(c).text() for c in range(cols)
        ]

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in range(rows):
                row_data = []
                for c in range(cols):
                    item = self._table.item(r, c)
                    row_data.append(item.text() if item else '')
                writer.writerow(row_data)

        self._status.setText(f"Exported {rows} parts to {path}")

    # ── Helpers ──────────────────────────────────────────────────────
    def _clear(self):
        self._cb_family.setCurrentIndex(0)
        self._table.setRowCount(0)
        self._btn_export.setEnabled(False)
        self._status.setText("Cleared.")

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._btn_search.setEnabled(True)
