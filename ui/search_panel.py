from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter,
    QTreeWidget, QTreeWidgetItem,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
import datetime

from db.search_loader import SearchParamLoader
from db.bom_loader    import BOMLoader

# ── shared constants (same as BOMPanel) ───────────────────────────────
_PLACEHOLDER  = '__placeholder__'
_ROLE_ITEM_NO = Qt.ItemDataRole.UserRole        # 256
_ROLE_HAS_BOM = Qt.ItemDataRole.UserRole + 1   # 257

_ANY = '— Any —'


class SearchPanel(QWidget):
    """
    Tab 3 — Search Space!

    Left side : cascading filter dropdowns  (Family → Size → Type)
                 results list after Search is clicked

    Right side : lazy BOM tree loaded when user clicks a result
                 (same lazy-expand logic as BOMPanel)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_scripts    = []       # full list of dicts from DB
        self._param_loader   = None
        self._active_loaders = []

        self._setup_ui()
        self._load_params()

    # ══════════════════════════════════════════════════════════════════
    # UI BUILD
    # ══════════════════════════════════════════════════════════════════
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Filter bar ─────────────────────────────────────────────
        bar = QHBoxLayout()

        self._cb_dataset = QComboBox()
        self._cb_dataset.addItems(['INL', 'KON'])
        self._cb_dataset.setFixedWidth(70)

        self._cb_family = QComboBox()
        self._cb_family.setMinimumWidth(110)
        self._cb_family.setToolTip("Product family  e.g. V30D, V30E, V30GL")

        self._cb_size = QComboBox()
        self._cb_size.setMinimumWidth(90)
        self._cb_size.setToolTip("Size / displacement  e.g. 095, 140")

        self._cb_type = QComboBox()
        self._cb_type.setMinimumWidth(120)
        self._cb_type.setToolTip("Control type code  e.g. RKN, RKGN, RSN")

        self._cb_sort = QComboBox()
        self._cb_sort.setFixedWidth(135)
        self._cb_sort.setToolTip("Sort matching results by date or name")
        self._cb_sort.addItem("Newest First",  "desc")
        self._cb_sort.addItem("Oldest First",  "asc")
        self._cb_sort.addItem("Name  A → Z",   "name")

        self._chk_unique = QCheckBox("Skip duplicates")
        self._chk_unique.setChecked(True)
        self._chk_unique.setToolTip(
            "Checked  → show each father item only once (first match per sort order)\n"
            "Unchecked → show every SCRIPTNUM entry including repeats"
        )

        self._btn_search = QPushButton("Search")
        self._btn_search.setFixedWidth(90)
        self._btn_search.setEnabled(False)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)

        bar.addWidget(QLabel("Dataset:"))
        bar.addWidget(self._cb_dataset)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Family:"))
        bar.addWidget(self._cb_family)
        bar.addWidget(QLabel("Size:"))
        bar.addWidget(self._cb_size)
        bar.addWidget(QLabel("Type:"))
        bar.addWidget(self._cb_type)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Sort:"))
        bar.addWidget(self._cb_sort)
        bar.addSpacing(6)
        bar.addWidget(self._chk_unique)
        bar.addSpacing(6)
        bar.addWidget(self._btn_search)
        bar.addWidget(self._btn_clear)
        bar.addStretch()
        root.addLayout(bar)

        # ── Status label ────────────────────────────────────────────
        self._status = QLabel("Loading parameters from database …")
        root.addWidget(self._status)

        # ── Horizontal splitter: results list | BOM tree ────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: results list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Matching BOMs:"))
        self._result_list = QListWidget()
        self._result_list.setAlternatingRowColors(True)
        left_layout.addWidget(self._result_list)
        splitter.addWidget(left)

        # Right: BOM tree panel (mini-bar + tree)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        tree_bar = QHBoxLayout()
        self._chk_tree_unique = QCheckBox("Skip duplicate rows")
        self._chk_tree_unique.setChecked(True)
        self._chk_tree_unique.setToolTip(
            "Checked  → hide rows where ScriptNum + ItemNo appear more than once\n"
            "Unchecked → show every raw row returned by the query"
        )
        tree_bar.addWidget(self._chk_tree_unique)
        tree_bar.addStretch()
        right_layout.addLayout(tree_bar)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            'ScriptNum', 'Item No', 'Qty', 'Has BOM', 'Description', 'Full Name'
        ])
        self._tree.setColumnWidth(0, 55)
        self._tree.setColumnWidth(1, 160)
        self._tree.setColumnWidth(2, 65)
        self._tree.setColumnWidth(3, 75)
        self._tree.setColumnWidth(4, 220)
        self._tree.setColumnWidth(5, 280)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        right_layout.addWidget(self._tree)

        splitter.addWidget(right)

        splitter.setSizes([340, 900])
        root.addWidget(splitter, 1)

        # ── Signals ─────────────────────────────────────────────────
        self._cb_dataset.currentIndexChanged.connect(self._on_dataset_changed)
        self._cb_family.currentIndexChanged.connect(self._on_family_changed)
        self._cb_size.currentIndexChanged.connect(self._on_size_changed)
        self._btn_search.clicked.connect(self._do_search)
        self._btn_clear.clicked.connect(self._clear)
        self._result_list.currentItemChanged.connect(self._on_result_selected)

    # ══════════════════════════════════════════════════════════════════
    # PARAMETER LOADING
    # ══════════════════════════════════════════════════════════════════
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

    # ── Cascading combo rebuilds ──────────────────────────────────────
    def _rebuild_family_combo(self):
        families = sorted(set(d['family'] for d in self._all_scripts if d['family']))
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
            key=lambda s: int(s) if s.isdigit() else 0
        )
        self._cb_size.blockSignals(True)
        self._cb_size.clear()
        self._cb_size.addItem(_ANY, None)
        for s in sizes:
            self._cb_size.addItem(s, s)
        self._cb_size.blockSignals(False)
        self._rebuild_type_combo()

    def _rebuild_type_combo(self):
        family = self._cb_family.currentData()
        size   = self._cb_size.currentData()
        filtered = self._all_scripts
        if family:
            filtered = [d for d in filtered if d['family'] == family]
        if size:
            filtered = [d for d in filtered if d['size'] == size]
        types = sorted(set(d['type_code'] for d in filtered if d['type_code']))
        self._cb_type.blockSignals(True)
        self._cb_type.clear()
        self._cb_type.addItem(_ANY, None)
        for t in types:
            self._cb_type.addItem(t, t)
        self._cb_type.blockSignals(False)

    # ── Combo change handlers ─────────────────────────────────────────
    def _on_dataset_changed(self, _):
        self._all_scripts = []
        self._result_list.clear()
        self._tree.clear()
        self._status.setText("Reloading parameters …")
        self._load_params()

    def _on_family_changed(self, _):
        self._rebuild_size_combo()

    def _on_size_changed(self, _):
        self._rebuild_type_combo()

    # ══════════════════════════════════════════════════════════════════
    # SEARCH
    # ══════════════════════════════════════════════════════════════════
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

        self._result_list.clear()
        self._tree.clear()

        if not results:
            self._status.setText("No matching BOMs found.")
            return

        # ── Sort ─────────────────────────────────────────────────────
        sort_key = self._cb_sort.currentData()
        _epoch   = datetime.datetime.min          # fallback for NULL dates

        if sort_key == "desc":
            results = sorted(results,
                             key=lambda d: d['created_date'] or _epoch,
                             reverse=True)
        elif sort_key == "asc":
            results = sorted(results,
                             key=lambda d: d['created_date'] or _epoch)
        else:   # "name"
            results = sorted(results, key=lambda d: d['txt1'])

        # ── Deduplicate by father item (keep first per sort order) ───
        if self._chk_unique.isChecked():
            seen    = set()
            unique  = []
            for d in results:
                if d['father'] not in seen:
                    seen.add(d['father'])
                    unique.append(d)
            dup_count = len(results) - len(unique)
            results   = unique
        else:
            dup_count = 0

        # ── Populate list ─────────────────────────────────────────────
        for d in results:
            dt   = d['created_date']
            date_str = dt.strftime('%Y-%m-%d  %H:%M') if dt else 'no date'
            label = f"[{date_str}]  {d['father']}  —  {d['txt1']}"
            item  = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, d['father'])
            item.setToolTip(
                f"ScriptNum : {d['scriptnum']}\n"
                f"Created   : {date_str}\n"
                f"Family    : {d['family']}   Size: {d['size']}   Type: {d['type_code']}\n"
                f"ItemName  : {d['itemname']}"
            )
            self._result_list.addItem(item)

        label_parts = []
        if family: label_parts.append(f"Family={family}")
        if size:   label_parts.append(f"Size={size}")
        if tcode:  label_parts.append(f"Type={tcode}")
        filter_str = "  ".join(label_parts) if label_parts else "no filter (all)"

        dup_str = f"  ({dup_count} duplicate(s) hidden)" if dup_count else ""
        self._status.setText(
            f"{len(results)} BOM(s) shown  [{filter_str}]{dup_str}  — click one to load its tree"
        )

    # ══════════════════════════════════════════════════════════════════
    # RESULT SELECTION → load BOM tree
    # ══════════════════════════════════════════════════════════════════
    def _on_result_selected(self, current: QListWidgetItem, _previous):
        if not current:
            return
        father_item = current.data(Qt.ItemDataRole.UserRole)
        if father_item:
            self._load_bom(father_item)

    def _load_bom(self, item_no: str):
        self._tree.clear()
        self._active_loaders.clear()
        self._status.setText(f"Loading BOM for  {item_no} …")

        # Root node — has_bom=False so NO placeholder is added.
        # A placeholder would trigger _on_item_expanded → second loader → doubled rows.
        root = self._make_node(
            parent=self._tree,
            script_num='',
            item_no=item_no,
            qty='',
            has_bom=False,
            description='Loading…',
            full_name=''
        )
        root.setExpanded(True)
        bold = QFont()
        bold.setBold(True)
        for col in range(self._tree.columnCount()):
            root.setFont(col, bold)

        self._start_loader(item_no, root)

    # ══════════════════════════════════════════════════════════════════
    # BOM TREE — lazy load (identical pattern to BOMPanel)
    # ══════════════════════════════════════════════════════════════════
    def _on_item_expanded(self, item: QTreeWidgetItem):
        if item.childCount() != 1:
            return
        placeholder = item.child(0)
        if placeholder.data(0, _ROLE_ITEM_NO) != _PLACEHOLDER:
            return
        item_no = item.data(0, _ROLE_ITEM_NO)
        item.removeChild(placeholder)
        self._status.setText(f"Loading children for  {item_no} …")
        self._start_loader(item_no, item)

    def _on_data_ready(self, parent_item: QTreeWidgetItem, rows: list):
        if not rows:
            self._status.setText(
                f"No BOM found for  {parent_item.data(0, _ROLE_ITEM_NO)}"
            )
            parent_item.setData(0, _ROLE_HAS_BOM, False)
            return

        first = rows[0]
        parent_item.setText(4, str(first.get('FatherDescription') or ''))
        parent_item.setText(5, str(first.get('FatherFullName')    or ''))

        # ── Deduplicate by (ScriptNum, ItemNo) if checkbox is checked ──
        if self._chk_tree_unique.isChecked():
            seen = set()
            unique_rows = []
            for row in rows:
                key = (str(row.get('ScriptNum') or ''), str(row.get('ItemNo') or ''))
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)
            dup_count = len(rows) - len(unique_rows)
            rows = unique_rows
        else:
            dup_count = 0

        for row in rows:
            has_bom = (row.get('BillType') == 1)
            child = self._make_node(
                parent=parent_item,
                script_num=str(row.get('ScriptNum')   or ''),
                item_no=str(row.get('ItemNo')         or ''),
                qty=str(row.get('Qty')                or ''),
                has_bom=has_bom,
                description=str(row.get('Description') or ''),
                full_name=str(row.get('FullName')       or ''),
            )
            if has_bom:
                for col in range(self._tree.columnCount()):
                    child.setForeground(col, QColor('#1565C0'))

        dup_str = f"  ({dup_count} duplicate(s) hidden)" if dup_count else ""
        self._status.setText(
            f"{parent_item.data(0, _ROLE_ITEM_NO)}  —  "
            f"{len(rows)} child item(s) loaded{dup_str}"
        )

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")
        self._btn_search.setEnabled(True)

    def _start_loader(self, item_no: str, parent_tree_item: QTreeWidgetItem):
        dataset = self._cb_dataset.currentText()
        loader  = BOMLoader(item_no, dataset)
        loader.data_ready.connect(
            lambda rows, p=parent_tree_item: self._on_data_ready(p, rows)
        )
        loader.error.connect(self._on_error)
        loader.finished.connect(lambda l=loader: self._cleanup_loader(l))
        loader.start()
        self._active_loaders.append(loader)

    def _cleanup_loader(self, loader: BOMLoader):
        try:
            self._active_loaders.remove(loader)
        except ValueError:
            pass

    # ══════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════
    def _make_node(self, parent, script_num, item_no, qty,
                   has_bom, description, full_name) -> QTreeWidgetItem:
        node = QTreeWidgetItem(parent)
        node.setText(0, script_num)
        node.setText(1, item_no)
        node.setText(2, qty)
        node.setText(3, 'Yes' if has_bom else 'No')
        node.setText(4, description)
        node.setText(5, full_name)
        node.setData(0, _ROLE_ITEM_NO, item_no)
        node.setData(0, _ROLE_HAS_BOM, has_bom)
        if has_bom:
            ph = QTreeWidgetItem(node)
            ph.setText(1, '…')
            ph.setData(0, _ROLE_ITEM_NO, _PLACEHOLDER)
        return node

    def _clear(self):
        self._cb_family.setCurrentIndex(0)  # cascades to size + type
        self._result_list.clear()
        self._tree.clear()
        self._status.setText("Cleared.")
