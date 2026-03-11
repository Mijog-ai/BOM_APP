from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter,
    QTreeWidget, QTreeWidgetItem, QFrame, QMenu, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
import datetime

from db.search_loader import SearchParamLoader
from db.bom_loader    import BOMLoader

# ── shared constants ────────────────────────────────────────────────
_PLACEHOLDER  = '__placeholder__'
_ROLE_ITEM_NO = Qt.ItemDataRole.UserRole        # 256
_ROLE_HAS_BOM = Qt.ItemDataRole.UserRole + 1   # 257

_ANY            = '— Any —'
_COLOUR_ACTIVE  = '#1565C0'    # blue border for active slot
_COLOUR_SUBBOM  = '#1565C0'    # blue text for items that have a sub-BOM
_COLOUR_INACTIVE_BORDER = '#BBBBBB'

# Background colors by BOM depth (matches bom_panel.py palette)
_DEPTH_COLORS = [
    '#FFFFFF',  # depth 0 — root
    '#F2F2F2',  # depth 1
    '#E5E5E5',  # depth 2
    '#D8D8D8',  # depth 3
    '#CBCBCB',  # depth 4
    '#BEBEBE',  # depth 5
    '#B2B2B2',  # depth 6+
]


# ══════════════════════════════════════════════════════════════════════
# _BomSlot — one self-contained BOM viewer panel
# ══════════════════════════════════════════════════════════════════════
class _BomSlot(QFrame):
    """
    One BOM viewer shown inside the horizontal splitter.

    Header bar: [Slot N button] [DS combo] [Skip dups] [item label]
    Body:       lazy QTreeWidget

    Clicking the 'Slot N' button emits `activated` so SearchPanel can
    update the active-slot highlight.
    """

    activated = pyqtSignal(object)   # emits self

    def __init__(self, slot_index: int, current_dataset: str, parent=None):
        super().__init__(parent)
        self.setObjectName("BomSlot")
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(2)

        self._slot_index     = slot_index
        self._active_loaders = []
        self._is_active      = False

        self._setup_ui(current_dataset)
        self._apply_style()

    # ── UI build ─────────────────────────────────────────────────────
    def _setup_ui(self, dataset: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        # ── Header bar ───────────────────────────────────────────────
        header = QHBoxLayout()

        self._btn_slot = QPushButton(f"Slot {self._slot_index + 1}")
        self._btn_slot.setFixedWidth(58)
        self._btn_slot.setFlat(True)
        self._btn_slot.setToolTip(
            "Click to make this the active slot.\n"
            "The active slot (blue border) receives the next result click."
        )
        self._btn_slot.clicked.connect(lambda: self.activated.emit(self))

        self._cb_dataset = QComboBox()
        self._cb_dataset.addItems(['INL', 'KON'])
        self._cb_dataset.setCurrentText(dataset)
        self._cb_dataset.setFixedWidth(62)
        self._cb_dataset.setToolTip("Dataset used when loading this BOM")

        self._chk_unique = QCheckBox("Skip dups")
        self._chk_unique.setChecked(True)
        self._chk_unique.setToolTip(
            "Checked → hide rows where Position+ItemNo repeat\n"
            "Unchecked → show every raw row"
        )

        self._item_input = QLineEdit()
        self._item_input.setPlaceholderText("type item no. + Enter")
        self._item_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._item_input.setToolTip("Type an item number and press Enter to load directly into this slot")
        self._item_input.returnPressed.connect(self._load_direct)

        header.addWidget(self._btn_slot)
        header.addSpacing(4)
        header.addWidget(QLabel("DS:"))
        header.addWidget(self._cb_dataset)
        header.addSpacing(6)
        header.addWidget(self._chk_unique)
        header.addSpacing(8)
        header.addWidget(self._item_input)
        layout.addLayout(header)

        # ── Status line ──────────────────────────────────────────────
        self._status = QLabel("Empty — click a result to load.")
        self._status.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self._status)

        # ── BOM tree ─────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            'Position', 'Item No', 'Qty', 'SCRIPTNUM', 'Description', 'Full Name'
        ])
        self._tree.setStyleSheet("""
            QTreeWidget::item:selected {
                background-color: #1565C0;
                color: white;
            }
        """)
        self._tree.setColumnWidth(0, 55)
        self._tree.setColumnWidth(1, 155)
        self._tree.setColumnWidth(2, 48)
        self._tree.setColumnWidth(3, 60)
        self._tree.setColumnWidth(4, 190)
        self._tree.setColumnWidth(5, 240)
        self._tree.setAlternatingRowColors(False)   # depth shading replaces this
        self._tree.setUniformRowHeights(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self._tree, 1)

    # ── Active-slot style ────────────────────────────────────────────
    def set_active(self, active: bool):
        self._is_active = active
        self._apply_style()

    def _apply_style(self):
        if self._is_active:
            self.setStyleSheet(
                "#BomSlot { border: 2px solid %s; }" % _COLOUR_ACTIVE
            )
            self._btn_slot.setStyleSheet(
                "font-weight: bold; color: %s;" % _COLOUR_ACTIVE
            )
        else:
            self.setStyleSheet(
                "#BomSlot { border: 2px solid %s; }" % _COLOUR_INACTIVE_BORDER
            )
            self._btn_slot.setStyleSheet(
                "font-weight: normal; color: #555555;"
            )

    # ── Index renaming (after a slot is removed) ──────────────────────
    def set_index(self, idx: int):
        self._slot_index = idx
        self._btn_slot.setText(f"Slot {idx + 1}")

    # ── Public API ────────────────────────────────────────────────────
    def _load_direct(self):
        item_no = self._item_input.text().strip()
        if item_no:
            self.load_item(item_no)

    def load_item(self, item_no: str):
        self._tree.clear()
        for loader in self._active_loaders:
            loader.quit()
        self._active_loaders.clear()

        self._item_input.setText(item_no)
        self._item_input.setStyleSheet("color: #111111; font-weight: bold;")
        self._status.setText(f"Loading BOM for  {item_no} …")

        root = self._make_node(
            parent=self._tree,
            position='', item_no=item_no, qty='',
            has_bom=False, description='Loading…', full_name='', scriptnum=''
        )
        root.setExpanded(True)
        bold = QFont()
        bold.setBold(True)
        for col in range(self._tree.columnCount()):
            root.setFont(col, bold)

        self._start_loader(item_no, root)

    def clear_tree(self):
        for loader in self._active_loaders:
            loader.quit()
        self._active_loaders.clear()
        self._tree.clear()
        self._item_input.clear()
        self._item_input.setStyleSheet("")
        self._status.setText("Cleared.")

    # ── Lazy expand ───────────────────────────────────────────────────
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

        if self._chk_unique.isChecked():
            seen, unique_rows = set(), []
            for row in rows:
                key = (str(row.get('Position') or ''), str(row.get('ItemNo') or ''))
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)
            dup_count = len(rows) - len(unique_rows)
            rows = unique_rows
        else:
            dup_count = 0

        for row in rows:
            has_bom = (row.get('Artikelart') == 1)
            child   = self._make_node(
                parent=parent_item,
                position=str(row.get('Position')       or ''),
                item_no=str(row.get('ItemNo')          or ''),
                qty=str(row.get('Qty')                 or ''),
                has_bom=has_bom,
                description=str(row.get('Description') or ''),
                full_name=str(row.get('FullName')       or ''),
                scriptnum=str(row.get('ScriptNum') or ''),
            )
            if has_bom:
                for col in range(self._tree.columnCount()):
                    child.setForeground(col, QColor(_COLOUR_SUBBOM))

        # Restore expanded state — Qt resets isExpanded() to False when the
        # placeholder child is removed (childCount drops to 0).
        parent_item.setExpanded(True)

        dup_str = f"  ({dup_count} dup(s) hidden)" if dup_count else ""
        self._status.setText(
            f"{parent_item.data(0, _ROLE_ITEM_NO)}  —  "
            f"{len(rows)} child(ren) loaded{dup_str}"
        )

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")

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

    def _cleanup_loader(self, loader):
        try:
            self._active_loaders.remove(loader)
        except ValueError:
            pass

    def _make_node(self, parent, position, item_no, qty,
                   has_bom, description, full_name, scriptnum='') -> QTreeWidgetItem:
        node = QTreeWidgetItem(parent)
        node.setText(0, position)
        node.setText(1, item_no)
        node.setText(2, qty)
        node.setText(3, str(scriptnum) if scriptnum else '')
        node.setText(4, description)
        node.setText(5, full_name)
        node.setData(0, _ROLE_ITEM_NO, item_no)
        node.setData(0, _ROLE_HAS_BOM, has_bom)

        # ── Depth-based gray shading ──────────────────────────────────
        depth = 0
        p = node.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        bg = QColor(_DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)])
        for col in range(self._tree.columnCount()):
            node.setBackground(col, bg)

        if has_bom:
            ph = QTreeWidgetItem(node)
            ph.setText(1, '…')
            ph.setData(0, _ROLE_ITEM_NO, _PLACEHOLDER)
        return node


# ══════════════════════════════════════════════════════════════════════
# SearchPanel — main widget (Tab 3)
# ══════════════════════════════════════════════════════════════════════
class SearchPanel(QWidget):
    """
    Tab 3 — Search Space

    Left  : cascading filter dropdowns (Family → Size → Type) + results list
    Right : horizontal splitter holding N _BomSlot panels — all visible at once

    Interaction
    ───────────
    • Left-click a result → loads into the active slot (blue-bordered)
    • Right-click a result → context menu to pick any slot by number
    • Click a slot's header button → make it the active slot
    • '＋ Add Slot' / '－ Remove Active' buttons manage the splitter panels
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_scripts     = []
        self._param_loader    = None
        self._bom_slots: list[_BomSlot] = []
        self._active_slot_idx = -1   # -1 = none yet; set during _setup_ui

        self._setup_ui()
        self._load_params()

    # ══════════════════════════════════════════════════════════════════
    # UI BUILD
    # ══════════════════════════════════════════════════════════════════
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ── Global filter bar ───────────────────────────────────────
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

        self._cb_sort = QComboBox()
        self._cb_sort.setFixedWidth(140)
        self._cb_sort.setToolTip("Sort matching results")
        self._cb_sort.addItem("Newest First", "desc")
        self._cb_sort.addItem("Oldest First", "asc")
        self._cb_sort.addItem("Name  A → Z",  "name")

        self._chk_unique = QCheckBox("Skip duplicates")
        self._chk_unique.setChecked(True)
        self._chk_unique.setToolTip(
            "Checked  → show each father item once (first match per sort)\n"
            "Unchecked → show every SCRIPTNUM entry including repeats"
        )

        self._btn_search = QPushButton("Search")
        self._btn_search.setFixedWidth(90)
        self._btn_search.setEnabled(False)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)

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
        bar.addWidget(QLabel("Sort:"))
        bar.addWidget(self._cb_sort)
        bar.addSpacing(4)
        bar.addWidget(self._chk_unique)
        bar.addSpacing(4)
        bar.addWidget(self._btn_search)
        bar.addWidget(self._btn_clear)
        bar.addStretch()
        root.addLayout(bar)

        # ── Status label ────────────────────────────────────────────
        self._status = QLabel("Loading parameters from database …")
        root.addWidget(self._status)

        # ── Main splitter: results list | BOM slots ──────────────────
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: results list
        left        = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)

        lbl_results = QLabel("Matching BOMs:")
        lbl_results.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(lbl_results)

        hint = QLabel("Left-click → active slot  ·  Right-click → choose slot")
        hint.setStyleSheet("color: #888888; font-size: 10px;")
        left_layout.addWidget(hint)

        self._result_list = QListWidget()
        self._result_list.setAlternatingRowColors(True)
        self._result_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._result_list.customContextMenuRequested.connect(self._show_slot_menu)
        left_layout.addWidget(self._result_list)
        main_splitter.addWidget(left)

        # Right: slot toolbar + horizontal BOM splitter
        right        = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        slot_bar = QHBoxLayout()
        self._btn_add_slot = QPushButton("＋  Add BOM Slot")
        self._btn_add_slot.setToolTip(
            "Add another BOM slot visible side by side"
        )
        self._btn_rem_slot = QPushButton("－  Remove Active Slot")
        self._btn_rem_slot.setToolTip("Remove the currently active (blue-bordered) slot")
        slot_bar.addWidget(self._btn_add_slot)
        slot_bar.addWidget(self._btn_rem_slot)
        slot_bar.addStretch()
        right_layout.addLayout(slot_bar)

        self._bom_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_layout.addWidget(self._bom_splitter, 1)
        main_splitter.addWidget(right)

        main_splitter.setSizes([320, 980])
        root.addWidget(main_splitter, 1)

        # ── Signals ─────────────────────────────────────────────────
        self._cb_dataset.currentIndexChanged.connect(self._on_dataset_changed)
        self._cb_family.currentIndexChanged.connect(self._on_family_changed)
        self._cb_size.currentIndexChanged.connect(self._on_size_changed)
        self._btn_search.clicked.connect(self._do_search)
        self._btn_clear.clicked.connect(self._clear)
        self._result_list.itemClicked.connect(self._on_result_clicked)
        self._btn_add_slot.clicked.connect(self._add_bom_slot)
        self._btn_rem_slot.clicked.connect(self._remove_active_slot)

        # Start with 2 visible slots
        self._add_bom_slot()
        self._add_bom_slot()
        self._set_active_slot(0)

    # ══════════════════════════════════════════════════════════════════
    # SLOT MANAGEMENT
    # ══════════════════════════════════════════════════════════════════
    def _add_bom_slot(self):
        idx  = len(self._bom_slots)
        slot = _BomSlot(
            slot_index=idx,
            current_dataset=self._cb_dataset.currentText(),
        )
        slot.activated.connect(self._on_slot_activated)
        self._bom_slots.append(slot)
        self._bom_splitter.addWidget(slot)
        self._set_active_slot(idx)
        self._btn_rem_slot.setEnabled(len(self._bom_slots) > 1)

    def _remove_active_slot(self):
        if len(self._bom_slots) <= 1:
            return
        idx  = self._active_slot_idx
        slot = self._bom_slots.pop(idx)
        slot.setParent(None)
        slot.deleteLater()
        # Re-index remaining slots
        for i, s in enumerate(self._bom_slots):
            s.set_index(i)
        # Activate nearest remaining slot
        self._active_slot_idx = -1
        self._set_active_slot(min(idx, len(self._bom_slots) - 1))
        self._btn_rem_slot.setEnabled(len(self._bom_slots) > 1)

    def _set_active_slot(self, idx: int):
        if self._active_slot_idx == idx:
            return
        self._active_slot_idx = idx
        for i, slot in enumerate(self._bom_slots):
            slot.set_active(i == idx)

    def _on_slot_activated(self, slot: _BomSlot):
        self._set_active_slot(self._bom_slots.index(slot))

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
        family   = self._cb_family.currentData()
        size     = self._cb_size.currentData()
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

        if not results:
            self._status.setText("No matching BOMs found.")
            return

        # Sort
        sort_key = self._cb_sort.currentData()
        _epoch   = datetime.datetime.min

        if sort_key == "desc":
            results = sorted(results,
                             key=lambda d: d['created_date'] or _epoch,
                             reverse=True)
        elif sort_key == "asc":
            results = sorted(results,
                             key=lambda d: d['created_date'] or _epoch)
        else:   # "name"
            results = sorted(results, key=lambda d: d['txt1'])

        # Deduplicate by father item
        if self._chk_unique.isChecked():
            seen, unique = set(), []
            for d in results:
                if d['father'] not in seen:
                    seen.add(d['father'])
                    unique.append(d)
            dup_count = len(results) - len(unique)
            results   = unique
        else:
            dup_count = 0

        # Populate list
        for d in results:
            dt       = d['created_date']
            date_str = dt.strftime('%Y-%m-%d  %H:%M') if dt else 'no date'
            label    = f"[{date_str}]  {d['father']}  —  {d['txt1']}"
            item     = QListWidgetItem(label)
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
        dup_str    = f"  ({dup_count} dup(s) hidden)" if dup_count else ""
        self._status.setText(
            f"{len(results)} BOM(s) shown  [{filter_str}]{dup_str}  "
            f"— left-click to load · right-click to pick slot"
        )

    # ══════════════════════════════════════════════════════════════════
    # RESULT SELECTION
    # ══════════════════════════════════════════════════════════════════
    def _on_result_clicked(self, item: QListWidgetItem):
        """Left-click → load into the active (blue-bordered) slot."""
        father_item = item.data(Qt.ItemDataRole.UserRole)
        if father_item and 0 <= self._active_slot_idx < len(self._bom_slots):
            self._load_into_slot(father_item, self._active_slot_idx)

    def _show_slot_menu(self, pos):
        """Right-click → context menu to choose target slot."""
        list_item = self._result_list.itemAt(pos)
        if not list_item:
            return
        father_item = list_item.data(Qt.ItemDataRole.UserRole)
        if not father_item:
            return

        menu = QMenu(self)

        # Section title (disabled, acts as header)
        title = menu.addAction(f"Load  '{father_item}'  into:")
        title.setEnabled(False)
        menu.addSeparator()

        for i, slot in enumerate(self._bom_slots):
            loaded = slot._item_input.text() or "— empty —"
            action = menu.addAction(f"Slot {i + 1}   (current: {loaded})")
            action.setData(i)

        chosen = menu.exec(self._result_list.mapToGlobal(pos))
        if chosen and chosen.data() is not None:
            self._load_into_slot(father_item, chosen.data())

    def _load_into_slot(self, item_no: str, slot_idx: int):
        if 0 <= slot_idx < len(self._bom_slots):
            self._bom_slots[slot_idx].load_item(item_no)
            self._set_active_slot(slot_idx)

    # ══════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════
    def _clear(self):
        self._cb_family.setCurrentIndex(0)
        self._result_list.clear()
        for slot in self._bom_slots:
            slot.clear_tree()
        self._status.setText("Cleared.")

    def _on_error(self, msg: str):
        self._status.setText(f"Error loading parameters: {msg}")
        self._btn_search.setEnabled(True)
