import json
import decimal

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from db.bom_loader   import BOMLoader
from db.bom_exporter import BOMExporter


class _JsonEncoder(json.JSONEncoder):
    """Handles Decimal and any other non-standard types pyodbc may return."""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)

# Sentinel stored in UserRole to mark placeholder children
_PLACEHOLDER = '__placeholder__'

# UserRole slots
_ROLE_ITEM_NO  = Qt.ItemDataRole.UserRole          # 256 — stores item number string
_ROLE_HAS_BOM  = Qt.ItemDataRole.UserRole + 1      # 257 — stores bool (BILLTYPE == 1)


class BOMPanel(QWidget):
    """
    BOM Tree tab.

    How lazy loading works:
    ┌─────────────────────────────────────────────────────┐
    │ 1. User enters item number → Load BOM button        │
    │ 2. Root node created, BOMLoader fires for it        │
    │ 3. Children added; if BILLTYPE==1 → placeholder     │
    │    child added so Qt shows the ▶ expand arrow       │
    │ 4. User clicks ▶  → itemExpanded fires              │
    │ 5. Placeholder removed, BOMLoader fires for that    │
    │    child → its children are added, and so on...     │
    └─────────────────────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_loaders = []   # keep refs so GC won't kill running threads
        self._exporter       = None
        self._setup_ui()

    # ------------------------------------------------------------------ setup
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # --- Top bar ---
        top = QHBoxLayout()
        self._item_input = QLineEdit()
        self._item_input.setPlaceholderText("Enter item number  e.g. 7956271.00")
        self._item_input.returnPressed.connect(self._load_root)

        self._dataset_cb = QComboBox()
        self._dataset_cb.addItems(['INL', 'KON'])
        self._dataset_cb.setFixedWidth(70)

        self._btn_load = QPushButton("Load BOM")
        self._btn_load.setFixedWidth(100)
        self._btn_load.clicked.connect(self._load_root)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self._clear)

        self._btn_export = QPushButton("Export Full JSON")
        self._btn_export.setFixedWidth(130)
        self._btn_export.setToolTip(
            "Recursively fetch the complete BOM tree from DB and save as JSON"
        )
        self._btn_export.clicked.connect(self._export_json)

        top.addWidget(QLabel("Item No:"))
        top.addWidget(self._item_input, 1)
        top.addWidget(QLabel("Dataset:"))
        top.addWidget(self._dataset_cb)
        top.addWidget(self._btn_load)
        top.addWidget(self._btn_clear)
        top.addWidget(self._btn_export)
        layout.addLayout(top)

        # --- Status ---
        self._status = QLabel("Enter an item number and click Load BOM.")
        layout.addWidget(self._status)

        # --- Tree ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            'Pos', 'Item No', 'Qty', 'Has BOM', 'Description', 'Full Name'
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
        layout.addWidget(self._tree)

    # ------------------------------------------------------------------ public
    def load_item(self, item_no: str):
        """Can be called externally (e.g. from table explorer double-click)."""
        self._item_input.setText(item_no)
        self._load_root()

    # ------------------------------------------------------------------ slots
    def _load_root(self):
        item_no = self._item_input.text().strip()
        if not item_no:
            return

        self._tree.clear()
        self._active_loaders.clear()
        self._status.setText(f"Loading BOM for  {item_no} ...")

        # Root node — description filled in when data arrives
        root = self._make_node(
            parent=self._tree,
            pos='', item_no=item_no,
            qty='', has_bom=True,
            description='Loading...', full_name=''
        )
        root.setExpanded(True)

        bold = QFont()
        bold.setBold(True)
        for col in range(self._tree.columnCount()):
            root.setFont(col, bold)

        self._start_loader(item_no, root)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Fired when user clicks ▶ on a tree node."""
        if item.childCount() != 1:
            return
        placeholder = item.child(0)
        if placeholder.data(0, _ROLE_ITEM_NO) != _PLACEHOLDER:
            return

        # Remove placeholder and load real children
        item_no = item.data(0, _ROLE_ITEM_NO)
        item.removeChild(placeholder)
        self._status.setText(f"Loading children for  {item_no} ...")
        self._start_loader(item_no, item)

    def _on_data_ready(self, parent_item: QTreeWidgetItem, rows: list):
        if not rows:
            self._status.setText(
                f"No BOM found for  {parent_item.data(0, _ROLE_ITEM_NO)}"
            )
            parent_item.setData(0, _ROLE_HAS_BOM, False)
            return

        # Update parent node label with father info from first row
        first = rows[0]
        parent_item.setText(4, str(first.get('FatherDescription') or ''))
        parent_item.setText(5, str(first.get('FatherFullName')    or ''))

        for row in rows:
            has_bom = (row.get('BillType') == 1)

            child = self._make_node(
                parent=parent_item,
                pos=str(row.get('Pos')         or ''),
                item_no=str(row.get('ItemNo')  or ''),
                qty=str(row.get('Qty')         or ''),
                has_bom=has_bom,
                description=str(row.get('Description') or ''),
                full_name=str(row.get('FullName')       or ''),
            )

            # Colour items that have a further BOM
            if has_bom:
                for col in range(self._tree.columnCount()):
                    child.setForeground(col, QColor('#1565C0'))  # blue

        self._status.setText(
            f"{parent_item.data(0, _ROLE_ITEM_NO)}  —  "
            f"{len(rows)} child item(s) loaded"
        )

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")

    def _export_json(self):
        item_no = self._item_input.text().strip()
        if not item_no:
            QMessageBox.information(self, "Export", "Enter an item number first.")
            return

        # Prevent double-click while running
        if self._exporter and self._exporter.isRunning():
            QMessageBox.information(self, "Export", "Export already in progress.")
            return

        dataset = self._dataset_cb.currentText()
        self._btn_export.setEnabled(False)
        self._status.setText(f"Preparing full JSON export for  {item_no} ...")

        self._exporter = BOMExporter(item_no, dataset)
        self._exporter.progress.connect(self._status.setText)
        self._exporter.export_ready.connect(self._on_export_ready)
        self._exporter.error.connect(self._on_export_error)
        self._exporter.start()

    def _on_export_ready(self, data: dict):
        self._btn_export.setEnabled(True)
        total = data.get('metadata', {}).get('total_items', '?')
        bom   = data.get('bom', {})

        # ── Rebuild visual tree with ALL levels — no placeholders, no clicking ──
        # Disconnect lazy-load signal while we programmatically populate the tree
        self._tree.itemExpanded.disconnect(self._on_item_expanded)
        self._tree.clear()
        self._active_loaders.clear()

        root = self._build_tree_from_dict(self._tree, bom, is_root=True)

        bold = QFont()
        bold.setBold(True)
        for col in range(self._tree.columnCount()):
            root.setFont(col, bold)

        self._tree.expandAll()
        self._tree.itemExpanded.connect(self._on_item_expanded)  # restore

        self._item_input.setText(bom.get('item_no', ''))
        self._status.setText(
            f"Full tree loaded — {total} items.  Choose where to save the JSON ..."
        )

        # ── Save dialog ──
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save BOM as JSON",
            f"BOM_{data['metadata']['item_no']}.json",
            "JSON Files (*.json)"
        )
        if not path:
            self._status.setText(
                f"Tree populated with {total} items.  JSON export cancelled."
            )
            return

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=_JsonEncoder, indent=2, ensure_ascii=False)

        self._status.setText(f"Saved {total} items → {path}")

    def _on_export_error(self, msg: str):
        self._btn_export.setEnabled(True)
        self._status.setText(f"Export error: {msg}")
        QMessageBox.critical(self, "Export Error", msg)

    def _clear(self):
        self._tree.clear()
        self._active_loaders.clear()
        self._status.setText("Cleared.")

    # ------------------------------------------------------------------ helpers
    def _start_loader(self, item_no: str, parent_tree_item: QTreeWidgetItem):
        dataset = self._dataset_cb.currentText()
        loader  = BOMLoader(item_no, dataset)

        # Capture parent_tree_item by value via default argument
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

    def _build_tree_from_dict(self, parent, node: dict,
                               is_root: bool = False) -> QTreeWidgetItem:
        """
        Recursively build QTreeWidgetItems from BOMExporter nested dict.
        No placeholders are added — every level is already fully loaded in 'node'.
        """
        item    = QTreeWidgetItem(parent)
        item_no = str(node.get('item_no') or '')
        has_bom = node.get('has_bom', False)
        children = node.get('children', [])

        item.setText(0, '' if is_root else str(node.get('pos') or ''))
        item.setText(1, item_no)
        item.setText(2, '' if is_root else str(node.get('qty') or ''))
        item.setText(3, 'Yes' if (has_bom or children) else 'No')
        item.setText(4, str(node.get('description') or ''))
        item.setText(5, str(node.get('full_name')   or ''))
        item.setData(0, _ROLE_ITEM_NO, item_no)
        item.setData(0, _ROLE_HAS_BOM, has_bom)

        # Blue = has sub-BOM; red = circular reference detected
        if node.get('circular_ref'):
            item.setText(4, '[Circular Reference — expansion stopped]')
            for col in range(self._tree.columnCount()):
                item.setForeground(col, QColor('#C62828'))
        elif has_bom and not is_root:
            for col in range(self._tree.columnCount()):
                item.setForeground(col, QColor('#1565C0'))

        for child_dict in children:
            self._build_tree_from_dict(item, child_dict, is_root=False)

        return item

    def _make_node(self, parent, pos, item_no, qty,
                   has_bom, description, full_name) -> QTreeWidgetItem:
        """Create and return a properly configured QTreeWidgetItem."""
        node = QTreeWidgetItem(parent)
        node.setText(0, pos)
        node.setText(1, item_no)
        node.setText(2, qty)
        node.setText(3, 'Yes' if has_bom else 'No')
        node.setText(4, description)
        node.setText(5, full_name)
        node.setData(0, _ROLE_ITEM_NO, item_no)
        node.setData(0, _ROLE_HAS_BOM, has_bom)

        # Add placeholder child so Qt shows the ▶ expand arrow
        if has_bom:
            ph = QTreeWidgetItem(node)
            ph.setText(1, '...')
            ph.setData(0, _ROLE_ITEM_NO, _PLACEHOLDER)

        return node
