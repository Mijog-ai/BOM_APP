import json
import os
import decimal
import tempfile
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QRadioButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from db.bom_loader import BOMLoader


def _write_indicator_svgs() -> tuple[str, str]:
    """
    Write checkbox indicator SVGs to the system temp folder and return
    (unchecked_url, checked_url) ready for use in a Qt stylesheet url().
    Written every run so changes survive temp-folder cleans.
    """
    unchecked = (
        '<svg width="13" height="13" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="1" y="1" width="11" height="11" rx="2"'
        ' fill="white" stroke="#888888" stroke-width="1.5"/>'
        '</svg>'
    )
    checked = (
        '<svg width="13" height="13" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="1" y="1" width="11" height="11" rx="2"'
        ' fill="white" stroke="#1565C0" stroke-width="1.5"/>'
        '<polyline points="3,7 5.5,9.5 10.5,4" fill="none"'
        ' stroke="#1565C0" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    tmp = tempfile.gettempdir()
    for fname, content in [('bom_chk_off.svg', unchecked),
                            ('bom_chk_on.svg',  checked)]:
        with open(os.path.join(tmp, fname), 'w', encoding='utf-8') as fh:
            fh.write(content)
    # Qt stylesheet urls need forward slashes even on Windows
    off = os.path.join(tmp, 'bom_chk_off.svg').replace('\\', '/')
    on  = os.path.join(tmp, 'bom_chk_on.svg').replace('\\', '/')
    return off, on


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

# Columns that should sort numerically (Position=0, Qty=2)
_NUMERIC_SORT_COLS = frozenset({0, 2})


def _fmt_qty(val) -> str:
    """Format a qty value: whole numbers show as int (e.g. 1.0 → '1'),
    fractional values keep their decimal (e.g. 1.5 → '1.5')."""
    if val is None or val == '':
        return ''
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else str(f)
    except (ValueError, TypeError):
        return str(val)


class _BOMTreeItem(QTreeWidgetItem):
    """QTreeWidgetItem with column-aware sorting.

    - Position (col 0) and Qty (col 2) sort numerically.
    - All other columns sort case-insensitively.
    - Placeholder loading items always sort to the bottom.
    """

    def __lt__(self, other: QTreeWidgetItem) -> bool:  # noqa: D105
        # Placeholders always go to the bottom regardless of sort direction
        self_is_ph  = self.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER
        other_is_ph = other.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER
        if self_is_ph and other_is_ph:
            return False
        if self_is_ph:
            return False   # self sinks to bottom
        if other_is_ph:
            return True    # other sinks to bottom

        tree = self.treeWidget()
        col  = tree.sortColumn() if tree else 1

        a = self.text(col)
        b = other.text(col)

        if col in _NUMERIC_SORT_COLS:
            try:
                return float(a or 0) < float(b or 0)
            except (ValueError, TypeError):
                pass
        return a.casefold() < b.casefold()

# Background colors by BOM depth (index = depth, clamped at last entry)
_DEPTH_COLORS = [
    '#FFFFFF',  # depth 0 — root
    '#F2F2F2',  # depth 1
    '#E5E5E5',  # depth 2
    '#D8D8D8',  # depth 3
    '#CBCBCB',  # depth 4
    '#BEBEBE',  # depth 5
    '#B2B2B2',  # depth 6+
]

# Column definitions for PDF settings dialog
# (label, default_with_pos, default_without_pos)  — None = not shown
# Order: left-side cols first (Position, Item No.), then right-side cols (Qty, Drawing).
# Description width is auto-computed and not listed here.
_PDF_COL_DEFS = [
    ('Position',              2.0,  None),
    ('Artikel-Nr./Item No.',  3.8,  5.0),
    ('Qty',                   1.0,  1.5),
    ('Drawing No.',           1.8,  2.5),
]


class PDFSettingsDialog(QDialog):
    """Lets the user tweak font sizes and column widths before exporting/previewing."""

    def __init__(self, include_pos: bool, preview_callback, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF Export Settings")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._include_pos = include_pos
        self._preview_cb  = preview_callback
        self._cols = [
            (lbl, d_pos if include_pos else d_no)
            for lbl, d_pos, d_no in _PDF_COL_DEFS
            if (include_pos and d_pos is not None) or (not include_pos and d_no is not None)
        ]
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Font sizes ────────────────────────────────────────────────
        font_box = QGroupBox("Font Sizes")
        fl = QHBoxLayout(font_box)
        fl.addWidget(QLabel("Header:"))
        self._hdr_fs = QSpinBox()
        self._hdr_fs.setRange(5, 18); self._hdr_fs.setValue(12); self._hdr_fs.setSuffix(" pt")
        self._hdr_fs.setFixedWidth(72)
        fl.addWidget(self._hdr_fs)
        fl.addSpacing(28)
        fl.addWidget(QLabel("Body:"))
        self._body_fs = QSpinBox()
        self._body_fs.setRange(5, 16); self._body_fs.setValue(11); self._body_fs.setSuffix(" pt")
        self._body_fs.setFixedWidth(72)
        fl.addWidget(self._body_fs)
        fl.addStretch()
        layout.addWidget(font_box)

        # ── Page Orientation ─────────────────────────────────────
        orient_box = QGroupBox("Page Orientation")
        ol = QHBoxLayout(orient_box)

        self._portrait = QRadioButton("Vertical (Portrait)")
        self._landscape = QRadioButton("Horizontal (Landscape)")

        self._portrait.setChecked(True)

        ol.addWidget(self._portrait)
        ol.addWidget(self._landscape)
        ol.addStretch()

        layout.addWidget(orient_box)

        # ── Column widths ─────────────────────────────────────────────
        col_box = QGroupBox("Column Widths (cm)")
        gl = QGridLayout(col_box)
        gl.setHorizontalSpacing(6)
        gl.setVerticalSpacing(6)
        gl.setColumnMinimumWidth(3, 18)   # gap between the two halves
        self._col_spins: dict[str, QDoubleSpinBox] = {}
        for i, (label, default) in enumerate(self._cols):
            r, c = divmod(i, 2)
            base = c * 4   # cols: 0/4=label, 1/5=spin, 2/6=unit, 3=gap
            gl.addWidget(QLabel(f"{label}:"), r, base)
            spin = QDoubleSpinBox()
            spin.setRange(0.5, 20.0); spin.setSingleStep(0.1)
            spin.setDecimals(1); spin.setValue(default); spin.setFixedWidth(74)
            self._col_spins[label] = spin
            gl.addWidget(spin, r, base + 1)
            gl.addWidget(QLabel("cm"), r, base + 2)
        layout.addWidget(col_box)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_prev = QPushButton("Preview")
        btn_prev.setToolTip("Generate a temporary PDF and open it in your PDF viewer")
        btn_prev.clicked.connect(self._on_preview)
        btn_row.addWidget(btn_prev)
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel"); btn_cancel.clicked.connect(self.reject)
        btn_export = QPushButton("Export"); btn_export.setDefault(True)
        btn_export.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_export)
        layout.addLayout(btn_row)

    def settings(self) -> dict:
        orientation = "portrait"
        if self._landscape.isChecked():
            orientation = "landscape"
        return {
            'header_font_size': self._hdr_fs.value(),
            'body_font_size':   self._body_fs.value(),
            "orientation": orientation,
            'col_widths':       [self._col_spins[lbl].value() for lbl, _ in self._cols],
        }

    def _on_preview(self):
        self._preview_cb(self.settings())


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

    Export reads the current tree widget state — expanded nodes include
    their children, collapsed nodes do not.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_loaders = []   # keep refs so GC won't kill running threads
        self._export_pending = False
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

        # Export format selector + button
        self._export_fmt = QComboBox()
        self._export_fmt.addItems(["PDF", "JSON", "Excel" ])
        self._export_fmt.setFixedWidth(68)
        self._export_fmt.setToolTip("Choose export format")

        self._btn_export = QPushButton("Export BOM")
        self._btn_export.setFixedWidth(110)
        self._btn_export.setToolTip(
            "Export the currently visible tree as JSON / Excel / PDF.\n"
            "Expanded nodes include their children; collapsed nodes do not."
        )
        self._btn_export.clicked.connect(self._export_bom)

        self._chk_unique = QCheckBox("Skip duplicate rows")
        self._chk_unique.setChecked(True)
        self._chk_unique.setToolTip(
            "Checked  → hide rows where Position + ItemNo appear more than once\n"
            "Unchecked → show every raw row returned by the query"
        )

        self._chk_pdf_pos = QCheckBox("Include Position col (PDF)")
        self._chk_pdf_pos.setChecked(True)
        self._chk_pdf_pos.setToolTip(
            "PDF only — Checked  → include the Position column\n"
            "           Unchecked → omit Position; gives more space to Description"
        )

        top.addWidget(QLabel("Item No:"))
        top.addWidget(self._item_input, 1)
        top.addWidget(QLabel("Dataset:"))
        top.addWidget(self._dataset_cb)
        top.addWidget(self._btn_load)
        top.addWidget(self._btn_clear)
        layout.addLayout(top)

        # --- Export bar ---
        export_bar = QHBoxLayout()
        export_bar.addWidget(self._chk_unique)
        export_bar.addStretch()
        export_bar.addWidget(self._chk_pdf_pos)
        export_bar.addSpacing(12)
        export_bar.addWidget(QLabel("Export:"))
        export_bar.addWidget(self._export_fmt)
        export_bar.addWidget(self._btn_export)
        layout.addLayout(export_bar)

        # --- Status ---
        self._status = QLabel("Enter an item number and click Load BOM.")
        layout.addWidget(self._status)

        # --- Tree ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            'Position', 'Item No', 'Qty', 'SCRIPTNUM', 'Description', 'Full Name'
        ])
        _chk_off, _chk_on = _write_indicator_svgs()
        self._tree.setStyleSheet(f"""
            QTreeWidget::item:selected {{
                background-color: #1565C0;
                color: white;
            }}
            QTreeWidget::indicator:unchecked {{
                image: url({_chk_off});
                width: 13px;
                height: 13px;
            }}
            QTreeWidget::indicator:checked {{
                image: url({_chk_on});
                width: 13px;
                height: 13px;
            }}
        """)
        self._tree.setColumnWidth(0, 55)
        self._tree.setColumnWidth(1, 160)
        self._tree.setColumnWidth(2, 65)
        self._tree.setColumnWidth(3, 75)
        self._tree.setColumnWidth(4, 220)
        self._tree.setColumnWidth(5, 280)
        # self._tree.setColumnWidth(6, 70)
        self._tree.setAlternatingRowColors(False)   # depth shading replaces this
        self._tree.setUniformRowHeights(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemChanged.connect(self._on_item_check_changed)

        # ── Column-header sorting ──────────────────────────────────────
        hdr = self._tree.header()
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.setToolTip(
            "Click a column header to sort A→Z.\n"
            "Click again to reverse (Z→A).\n"
            "Position and Qty sort numerically."
        )
        hdr.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

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
        # self._export_pending = False
        self._status.setText(f"Loading BOM for  {item_no} ...")

        # Root node — has_bom=False so NO placeholder is added.
        root = self._make_node(
            parent=self._tree,
            pos='', item_no=item_no,
            qty='', has_bom=False,
            description='Loading...', full_name='', scriptnum=''
        )
        root.setExpanded(True)

        bold = QFont()
        bold.setBold(True)
        for col in range(self._tree.columnCount()):
            root.setFont(col, bold)

        self._start_loader(item_no, root)

    def _on_sort_indicator_changed(self, col: int, order: Qt.SortOrder):
        """Qt has already toggled the indicator — just apply the sort."""
        self._tree.sortItems(col, order)

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

        self._tree.blockSignals(True)
        try:
            # Update parent node label with father info from first row
            first = rows[0]
            parent_item.setText(4, str(first.get('FatherDescription') or ''))
            parent_item.setText(5, str(first.get('FatherFullName')    or ''))

            # Re-apply blue foreground — setText() can silently reset the color
            if parent_item.data(0, _ROLE_HAS_BOM):
                for col in range(self._tree.columnCount()):
                    parent_item.setForeground(col, QColor('#1565C0'))

            # ── Deduplicate by (Position, ItemNo) if checkbox is checked ──
            if self._chk_unique.isChecked():
                seen = set()
                unique_rows = []
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

                child = self._make_node(
                    parent=parent_item,
                    pos=str(row.get('Position')    or ''),
                    item_no=str(row.get('ItemNo')  or ''),
                    qty=_fmt_qty(row.get('Qty')),
                    has_bom=has_bom,
                    description=str(row.get('Description') or ''),
                    full_name=str(row.get('FullName')       or ''),
                    scriptnum=str(row.get('ScriptNum') or ''),
                )

                if has_bom:
                    for col in range(self._tree.columnCount()):
                        child.setForeground(col, QColor('#1565C0'))  # blue

            # ── Restore expanded state ────────────────────────────────────
            # Qt resets isExpanded() to False when the placeholder child is
            # removed (childCount drops to 0).  Re-expand now that real
            # children exist, so _widget_item_to_dict will recurse into them.
            parent_item.setExpanded(True)

            # ── Inherit parent's check state for newly loaded children ──
            if parent_item.checkState(0) == Qt.CheckState.Unchecked:
                self._cascade_check(parent_item, Qt.CheckState.Unchecked)

        finally:
            self._tree.blockSignals(False)

        dup_str = f"  ({dup_count} duplicate(s) hidden)" if dup_count else ""
        self._status.setText(
            f"{parent_item.data(0, _ROLE_ITEM_NO)}  —  "
            f"{len(rows)} child item(s) loaded{dup_str}"
        )

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")

    # ------------------------------------------------------------------ export
    def _export_bom(self):
        if self._tree.invisibleRootItem().childCount() == 0:
            QMessageBox.information(self, "Export", "Load a BOM first.")
            return

        # Expand any unloaded (checked) placeholder nodes before exporting
        root = self._tree.invisibleRootItem().child(0)
        fired = self._expand_all_placeholders(root) if root else 0

        if fired > 0 or self._active_loaders:
            self._export_pending = True
            self._status.setText("Loading unread nodes before export…")
            return

        self._do_export()

    def _expand_all_placeholders(self, item: QTreeWidgetItem) -> int:
        """Recursively fire loaders for checked nodes whose children are not yet loaded.
        Returns the number of loaders started."""
        if item is None:
            return 0
        # Skip unchecked nodes — they won't appear in the export anyway
        if item.checkState(0) == Qt.CheckState.Unchecked:
            return 0

        fired = 0
        if item.childCount() == 1 and item.child(0).data(0, _ROLE_ITEM_NO) == _PLACEHOLDER:
            item_no = item.data(0, _ROLE_ITEM_NO)
            item.removeChild(item.child(0))
            self._start_loader(item_no, item)
            fired += 1
        else:
            for i in range(item.childCount()):
                fired += self._expand_all_placeholders(item.child(i))
        return fired

    def _do_export(self):
        """Dispatch to the correct save handler once all nodes are loaded."""
        fmt  = self._export_fmt.currentText()
        data = self._build_export_data_from_tree()

        if fmt == 'JSON':
            path, _ = QFileDialog.getSaveFileName(
                self, "Save BOM as JSON",
                f"BOM_{data['metadata']['item_no']}.json",
                "JSON Files (*.json)",
            )
            if not path:
                return
            try:
                self._save_as_json(data, path)
                self._status.setText(f"Saved {data['metadata']['total_items']} items → {path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
                self._status.setText(f"Export error: {e}")

        elif fmt == 'Excel':
            path, _ = QFileDialog.getSaveFileName(
                self, "Save BOM as Excel",
                f"BOM_{data['metadata']['item_no']}.xlsx",
                "Excel Files (*.xlsx)",
            )
            if not path:
                return
            try:
                self._save_as_excel(data, path)
                self._status.setText(f"Saved {data['metadata']['total_items']} items → {path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
                self._status.setText(f"Export error: {e}")

        elif fmt == 'PDF':
            self._export_as_pdf(data)



    def _export_as_pdf(self, data: dict):
        """Show PDF settings dialog (with preview), then save."""
        include_pos = self._chk_pdf_pos.isChecked()

        def _preview(settings: dict):
            fd, tmp_path = tempfile.mkstemp(suffix='.pdf', prefix='bom_preview_')
            os.close(fd)
            try:
                self._save_as_pdf(data, tmp_path, settings)
                os.startfile(tmp_path)
            except Exception as e:
                QMessageBox.critical(self, "Preview Error", str(e))

        dlg = PDFSettingsDialog(include_pos, _preview, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dlg.settings()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save BOM as PDF",
            f"BOM_{data['metadata']['item_no']}.pdf",
            "PDF Files (*.pdf)",
        )
        if not path:
            return

        try:
            self._save_as_pdf(data, path, settings)
            self._status.setText(f"Saved {data['metadata']['total_items']} items → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            self._status.setText(f"Export error: {e}")

    # ------------------------------------------------------------------ tree → data
    def _build_export_data_from_tree(self) -> dict:
        """Read the current QTreeWidget and build the export data dict."""
        root_qt = self._tree.invisibleRootItem().child(0)
        bom     = self._widget_item_to_dict(root_qt, is_root=True) if root_qt else {}
        if bom is None:
            bom = {}
        # Use the flattened row count so "Items: N" matches what appears in
        # the exported table (negative-qty rows are excluded by _flatten_bom).
        total   = len(self._flatten_bom(bom))
        return {
            'metadata': {
                'item_no':     self._item_input.text().strip(),
                'description': bom.get('description', ''),
                'dataset':     self._dataset_cb.currentText(),
                'exported_at': datetime.now().isoformat(timespec='seconds'),
                'total_items': total,
            },
            'bom': bom,
        }

    def _widget_item_to_dict(self, item: QTreeWidgetItem, is_root: bool = False):
        if item.checkState(0) == Qt.CheckState.Unchecked:
            return None

        qty_text = item.text(2)
        try:
            qty = float(qty_text) if qty_text else ''
        except ValueError:
            qty = qty_text

        node = {
            'position': '' if is_root else item.text(0),
            'item_no': item.text(1),
            'qty': qty,
            'scriptnum': item.text(3),
            'has_bom': item.data(0, _ROLE_HAS_BOM) or False,
            'description': item.text(4),
            'full_name': item.text(5),
            'children': [],
        }

        # Recurse if children have been loaded, even if the node is collapsed
        has_real_children = any(
            item.child(i).data(0, _ROLE_ITEM_NO) != _PLACEHOLDER
            for i in range(item.childCount())
        )
        if item.isExpanded() or has_real_children:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER:
                    continue
                child_dict = self._widget_item_to_dict(child)
                if child_dict is not None:
                    node['children'].append(child_dict)

        return node

    def _count_nodes(self, node: dict) -> int:
        if not node:
            return 0
        return 1 + sum(self._count_nodes(c) for c in node.get('children', []))

    # ------------------------------------------------------------------ save helpers
    def _save_as_json(self, data: dict, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=_JsonEncoder, indent=2, ensure_ascii=False)

    def _flatten_bom(self, node: dict, level: int = 0, parent_position: str = '',
                     _depth_last: list = None) -> list:
        """Recursively flatten nested BOM dict into a list of row dicts.
        Rows with negative qty are excluded (along with their children).
        _depth_last: list of bools — True means that depth-level node was the last sibling.
        """
        if _depth_last is None:
            _depth_last = []

        qty = node.get('qty', '')
        if isinstance(qty, (int, float)) and qty < 0:
            return []

        position = str(node.get('position') or '').strip()
        item_no = str(node.get('item_no') or '').strip()

        # Build hierarchical position path, e.g. 010.020.030
        if parent_position and position:
            position_path = f"{parent_position}.{position}"
        else:
            position_path = position

        # Pre-filter negative-qty children BEFORE building row dict
        # (visible_children is referenced in the row dict below)
        visible_children = [
            c for c in node.get('children', [])
            if not (isinstance(c.get('qty', ''), (int, float)) and c.get('qty', '') < 0)
        ]

        row = {
            'level': level,
            'position': position,
            'position_path': position_path,
            'item_no': item_no,
            'qty': qty,
            'scriptnum': str(node.get('scriptnum') or '').strip(),
            'description': str(node.get('description') or '').strip(),
            'full_name': str(node.get('full_name') or '').strip(),
            '_has_bom_raw': node.get('has_bom', False) or bool(visible_children),
            '_depth_last': list(_depth_last),
        }

        result = [row]

        for idx, child in enumerate(visible_children):
            is_last = (idx == len(visible_children) - 1)
            result.extend(self._flatten_bom(child, level + 1, position_path,
                                            _depth_last + [is_last]))

        return result

    def _save_as_excel(self, data: dict, path: str):
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

        meta = data.get('metadata', {})
        rows = self._flatten_bom(data.get('bom', {}))
        if rows and rows[0].get("level") == 0:
            rows = rows[1:]

        wb = Workbook()
        ws = wb.active
        ws.title = "BOM"

        # ── Metadata header rows ──────────────────────────────────────
        ws.append([f"BOM Export — {meta.get('item_no', '')}"])
        ws.append([
            f"{meta.get('description', '')}  |  "
            f"Exported: {meta.get('exported_at', '')}"
        ])
        ws.append([])   # blank spacer

        # ── Column header row ─────────────────────────────────────────
        col_headers = ['Level', 'Position', 'Item No', 'Qty', 'SCRIPTNUM', 'Description', 'Full Name']
        ws.append(col_headers)
        hdr_row = ws.max_row
        hdr_fill = PatternFill(fill_type='solid', fgColor='1565C0')
        hdr_font = Font(bold=True, color='FFFFFF')
        for cell in ws[hdr_row]:
            cell.fill      = hdr_fill
            cell.font      = hdr_font
            cell.alignment = Alignment(horizontal='center')

        # ── Data rows ─────────────────────────────────────────────────
        thin = Side(style='thin', color='CCCCCC')
        grid = Border(left=thin, right=thin, top=thin, bottom=thin)

        for row in rows:
            depth   = row['level']
            hex_col = _DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)].lstrip('#')
            fill    = PatternFill(fill_type='solid', fgColor=hex_col)

            ws.append([
                depth, row['position'], row['item_no'],
                row['qty'], row['scriptnum'],
                row['description'], row['full_name'],
            ])

            r = ws.max_row
            for cell in ws[r]:
                cell.fill   = fill
                cell.border = grid
                if depth == 0:
                    cell.font = Font(bold=True)

        # ── Column widths ─────────────────────────────────────────────
        for col_idx, width in enumerate([8, 12, 28, 10, 10, 45, 38], start=1):
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = width

        wb.save(path)

    def _save_as_pdf(self, data: dict, path: str, settings: dict = None):
        from reportlab.lib.pagesizes import A4, landscape, portrait
        from reportlab.lib import colors
        from reportlab.lib.units import mm, cm
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth

        # ── defaults ──────────────────────────────────────────────────
        if settings is None:
            settings = {
                'header_font_size': 9,
                'body_font_size':   8,
                'col_widths':       None,
                'orientation':      'landscape',
            }

        fs_hdr      = settings.get('header_font_size', 9)
        fs_body     = settings.get('body_font_size',   8)
        orientation = settings.get('orientation',      'landscape')
        include_pos = self._chk_pdf_pos.isChecked()

        page_size = portrait(A4) if orientation == 'portrait' else landscape(A4)
        pw, ph    = page_size

        meta = data.get('metadata', {})
        rows = self._flatten_bom(data.get('bom', {}))

        # ── layout ────────────────────────────────────────────────────
        lm      = 15 * mm          # left margin
        rm      = 15 * mm          # right margin
        row_h   = 7.5 * mm         # data row height
        hdr_h   = 8 * mm           # column-header bar height
        title_h = 18 * mm          # title block on first page only
        bot_m   = 12 * mm          # bottom margin
        graph_w = 22 * mm          # dedicated connector-graphic column

        # Layout (matches test_drawing_in_pdf.py style):
        #   lm | [Position] [Item No.] | [Description — auto width] | [Graph] | [Qty] [Drawing] | rm
        # Left-of-description fixed cols, right-of-graph fixed cols; description fills the middle.
        if include_pos:
            default_cw = [2.0, 3.8, 1.0, 1.8]   # Pos | Item | Qty | Drawing
            n_left     = 2                          # columns left of description
        else:
            default_cw = [5.0, 1.2, 1.8]          # Item | Qty | Drawing
            n_left     = 1

        raw_cw = settings.get('col_widths')
        if raw_cw and len(raw_cw) >= len(default_cw):
            cw_vals = [w * cm for w in raw_cw[:len(default_cw)]]
        else:
            cw_vals = [w * cm for w in default_cw]

        left_cw_pt = cw_vals[:n_left]        # Pos [, Item] — left of description
        qty_w_pt   = cw_vals[n_left]         # Qty  — right of graph
        drw_w_pt   = cw_vals[n_left + 1]    # Drawing No. — rightmost

        # x-positions — right side anchored to page right margin
        table_right = pw - rm
        x_drw       = table_right - drw_w_pt         # Drawing No. starts here
        x_qty       = x_drw - qty_w_pt               # Qty starts here
        x_grph      = x_qty - graph_w                # graph column starts here

        # Left-side x-positions
        xs_left = [lm]
        for w in left_cw_pt:
            xs_left.append(xs_left[-1] + w)

        x_desc  = xs_left[-1]                        # Description starts after last left col
        desc_w  = x_grph - x_desc                   # Description fills remaining space

        if include_pos:
            left_hdr_labels = ['Position', 'Artikel-Nr./Item No.']
        else:
            left_hdr_labels = ['Artikel-Nr./Item No.']

        # ── connector spine positions ──────────────────────────────────
        # Level 0 = rightmost spine; each deeper level steps LEFT by 6 mm.
        # Matches the test-script style: x_v2 (level 0) > x_v1 (level 1).
        def spine_x(level: int) -> float:
            return (x_grph + graph_w - 5 * mm) - level * 6 * mm

        # ── colors ────────────────────────────────────────────────────
        line_clr = colors.HexColor('#888888')
        asm_clr  = colors.HexColor('#2d74da')
        grid_clr = colors.HexColor('#e0e0e0')

        # ── helpers ───────────────────────────────────────────────────
        def fit_text(text, max_w, font, size):
            """Truncate *text* so it fits in *max_w* points; append '…' if cut."""
            if not text:
                return ''
            if stringWidth(text, font, size) <= max_w:
                return text
            while text and stringWidth(text + '\u2026', font, size) > max_w:
                text = text[:-1]
            return (text + '\u2026') if text else ''

        def draw_arrow(c, x_spine, y):
            """Left-pointing arrow. Shaft ends at x_spine; tip points left."""
            x_tip = x_grph + 2 * mm          # tip always near left edge of graph col
            ah    = 1.5 * mm
            if x_spine <= x_tip + ah:         # not enough room — skip
                return
            c.setStrokeColor(asm_clr)
            c.setLineWidth(1.0)
            c.line(x_tip + ah, y, x_spine, y)            # shaft
            c.line(x_tip, y, x_tip + ah, y + ah * 0.8)  # upper barb
            c.line(x_tip, y, x_tip + ah, y - ah * 0.8)  # lower barb

        def draw_dot(c, x, y, r=2.0, color=None):
            clr = color or line_clr
            c.setFillColor(clr)
            c.setStrokeColor(clr)
            c.circle(x, y, r, fill=1, stroke=0)

        def draw_connectors(c, page_rows, centers):
            """
            Draw vertical spines, left-pointing arrows, and dots for one page.
            Follows the same two-pass approach as test_drawing_in_pdf.py:
              Pass 1 — vertical spine from each assembly to its last direct child.
              Pass 2 — arrow for every assembly, dot on parent spine for every
                        non-root row.
            """
            n = len(page_rows)
            c.saveState()

            # Pass 1: vertical spines
            for di, row in enumerate(page_rows):
                if not row.get('_has_bom_raw', False):
                    continue
                depth = row['level']
                sx    = spine_x(depth)
                last_child_cy = None
                for dj in range(di + 1, n):
                    cdepth = page_rows[dj]['level']
                    if cdepth == depth + 1:
                        last_child_cy = centers[dj]
                    elif cdepth <= depth:
                        break
                if last_child_cy is not None:
                    clr = asm_clr if depth == 0 else line_clr
                    c.setStrokeColor(clr)
                    c.setLineWidth(0.8)
                    c.line(sx, centers[di], sx, last_child_cy)

            # Pass 2: arrows + dots
            for di, row in enumerate(page_rows):
                depth   = row['level']
                has_bom = row.get('_has_bom_raw', False)
                cy      = centers[di]
                if has_bom:
                    draw_arrow(c, spine_x(depth), cy)  # shaft ends at spine, tip→left
                if depth > 0:
                    draw_dot(c, spine_x(depth - 1), cy,
                             color=asm_clr if has_bom else line_clr)

            c.restoreState()

        # ── pagination ────────────────────────────────────────────────
        usable_first = ph - bot_m - title_h - hdr_h
        usable_other = ph - bot_m - 8 * mm  - hdr_h
        rows_fp = max(1, int(usable_first / row_h))
        rows_op = max(1, int(usable_other / row_h))

        pages = []
        idx = 0
        while idx < len(rows):
            cap = rows_fp if not pages else rows_op
            pages.append(rows[idx: idx + cap])
            idx += cap
        if not pages:
            pages = [[]]
        n_pages = len(pages)

        # ── draw ──────────────────────────────────────────────────────
        c = Canvas(path, pagesize=page_size)

        for pi, page_rows in enumerate(pages):
            is_first = (pi == 0)

            # Title block (first page only)
            if is_first:
                ty = ph - 8 * mm
                c.setFont('Helvetica-Bold', 11)
                c.setFillColor(colors.black)
                c.drawString(lm, ty,
                    f"BOM Export \u2014 {meta.get('item_no', '')} "
                    f"| {meta.get('description', '')}")
                ty -= 6 * mm
                c.setFont('Helvetica', 8)
                c.setFillColor(colors.HexColor('#555555'))
                c.drawString(lm, ty,
                    f"Exported: {meta.get('exported_at', '')}  "
                    f"\u2022  Items: {meta.get('total_items', '')}")
                hdr_top = ph - title_h
            else:
                hdr_top = ph - 8 * mm

            # Column-header — plain style matching test_drawing_in_pdf.py
            hdr_y = hdr_top - hdr_h + 2.5
            c.setFont('Helvetica-Bold', fs_hdr)
            c.setFillColor(colors.black)
            for lbl, xc in zip(left_hdr_labels, xs_left):
                c.drawString(xc + 2, hdr_y, lbl)
            c.drawString(x_desc + 2, hdr_y, 'Bezeichnung / Designation')
            c.drawString(x_qty  + 2, hdr_y, 'St.')
            c.drawString(x_drw  + 2, hdr_y, 'Drawing No.')
            # Gray underline below header
            c.setStrokeColor(colors.HexColor('#cfcfcf'))
            c.setLineWidth(0.8)
            c.line(lm, hdr_top - hdr_h, table_right, hdr_top - hdr_h)

            # Row y-positions: text baseline sits at mid-height of each band
            y_top       = hdr_top - hdr_h
            y_positions = [y_top - (i + 0.5) * row_h for i in range(len(page_rows))]
            centers     = [y + 0.5 for y in y_positions]   # slight lift for dots/arrows

            # Data rows
            for i, row in enumerate(page_rows):
                y     = y_positions[i]
                depth = row['level']
                fnt   = 'Helvetica-Bold' if depth == 0 else 'Helvetica'

                # Row bottom separator — light gray line, no background fill
                c.setStrokeColor(colors.HexColor('#e6e6e6'))
                c.setLineWidth(0.6)
                c.line(lm, y - row_h * 0.55, table_right, y - row_h * 0.55)

                # Cell text
                c.setFillColor(colors.black)
                c.setFont(fnt, fs_body)

                # Left-side cells (Position [, Item No.])
                if include_pos:
                    left_vals = [
                        str(row.get('position_path') or row.get('position') or ''),
                        str(row['item_no']),
                    ]
                else:
                    left_vals = [str(row['item_no'])]
                for val, xc, cw in zip(left_vals, xs_left, left_cw_pt):
                    c.drawString(xc + 2, y, fit_text(val, cw - 4, fnt, fs_body))

                # Description — German on top line, English below
                desc_de = str(row.get('description') or '').strip()
                desc_en = str(row.get('full_name')   or '').strip()
                if desc_de and desc_en and desc_de != desc_en:
                    fs_en = max(fs_body - 1, 5)
                    c.setFont(fnt, fs_body)
                    c.drawString(x_desc + 2, y + fs_body * 0.4,
                                 fit_text(desc_de, desc_w - 4, fnt, fs_body))
                    c.setFont(fnt, fs_en)
                    c.setFillColor(colors.HexColor('#555555'))
                    c.drawString(x_desc + 2, y - fs_en * 0.9,
                                 fit_text(desc_en, desc_w - 4, fnt, fs_en))
                    c.setFillColor(colors.black)
                    c.setFont(fnt, fs_body)
                else:
                    c.drawString(x_desc + 2, y,
                                 fit_text(desc_de or desc_en, desc_w - 4, fnt, fs_body))

                # Right-side cells (Qty, Drawing No.) — after graph column
                c.drawString(x_qty + 2, y,
                             fit_text(_fmt_qty(row['qty']), qty_w_pt - 4, fnt, fs_body))
                c.drawString(x_drw + 2, y,
                             fit_text(str(row['scriptnum']), drw_w_pt - 4, fnt, fs_body))

            # Bottom table border
            if page_rows:
                last_y = y_positions[-1] - row_h * 0.55
                c.setStrokeColor(colors.HexColor('#cfcfcf'))
                c.setLineWidth(0.8)
                c.line(lm, last_y, table_right, last_y)

            # Vertical column dividers
            div_top = hdr_top
            div_bot = (y_positions[-1] - row_h * 0.55) if page_rows else (hdr_top - hdr_h)
            c.setStrokeColor(colors.HexColor('#cfcfcf'))
            c.setLineWidth(0.4)
            c.line(lm,          div_top, lm,          div_bot)
            c.line(table_right, div_top, table_right, div_bot)
            for xc in xs_left[1:]:
                c.line(xc, div_top, xc, div_bot)
            c.line(x_desc,  div_top, x_desc,  div_bot)
            c.line(x_grph,  div_top, x_grph,  div_bot)
            c.line(x_qty,   div_top, x_qty,   div_bot)
            c.line(x_drw,   div_top, x_drw,   div_bot)

            # Connector graphics (arrows + spines + dots) in graph column
            draw_connectors(c, page_rows, centers)

            # Page number
            c.setFont('Helvetica', 7)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawRightString(pw - rm, 4 * mm, f"Page {pi + 1} von {n_pages}")

            c.showPage()

        c.save()

    # ------------------------------------------------------------------ check logic
    def _on_item_check_changed(self, item: QTreeWidgetItem, column: int):
        """User clicked a checkbox — cascade to descendants / ancestors."""
        if column != 0:
            return
        if item.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER:
            return

        self._tree.blockSignals(True)
        state = item.checkState(0)

        # Uncheck → propagate down to all loaded descendants
        # Check  → propagate down AND fix parent chain
        if state == Qt.CheckState.Unchecked:
            self._cascade_check(item, Qt.CheckState.Unchecked)
        else:
            self._cascade_check(item, Qt.CheckState.Checked)
            p = item.parent()
            while p is not None:
                p.setCheckState(0, Qt.CheckState.Checked)
                p = p.parent()

        self._tree.blockSignals(False)

    def _cascade_check(self, item: QTreeWidgetItem, state: Qt.CheckState):
        """Recursively apply *state* to all loaded (non-placeholder) descendants."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER:
                continue
            child.setCheckState(0, state)
            self._cascade_check(child, state)

    # ------------------------------------------------------------------ misc
    def _clear(self):
        self._tree.clear()
        self._active_loaders.clear()
        self._export_pending = False
        self._status.setText("Cleared.")

    # ------------------------------------------------------------------ helpers
    def _start_loader(self, item_no: str, parent_tree_item: QTreeWidgetItem):
        dataset = self._dataset_cb.currentText()
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
        if self._export_pending and not self._active_loaders:
            self._export_pending = False
            self._export_bom()

    def _make_node(self, parent, pos, item_no, qty,
                   has_bom, description, full_name, scriptnum='') -> QTreeWidgetItem:
        """Create and return a properly configured QTreeWidgetItem."""
        node = _BOMTreeItem(parent)
        node.setText(0, pos)
        node.setText(1, item_no)
        node.setText(2, qty)
        node.setText(3, str(scriptnum) if scriptnum else '')
        node.setText(4, description)
        node.setText(5, full_name)
        node.setData(0, _ROLE_ITEM_NO, item_no)
        node.setData(0, _ROLE_HAS_BOM, has_bom)
        node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        node.setCheckState(0, Qt.CheckState.Checked)

        # ── Depth-based gray shading ──────────────────────────────────────
        depth = 0
        p = node.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        bg = QColor(_DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)])
        for col in range(self._tree.columnCount()):
            node.setBackground(col, bg)

        if has_bom:
            ph = _BOMTreeItem(node)
            ph.setText(1, '...')
            ph.setData(0, _ROLE_ITEM_NO, _PLACEHOLDER)

        return node