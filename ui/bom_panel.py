import json
import os
import decimal
import tempfile
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox
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
_PDF_COL_DEFS = [
    ('Position',    2.0,  None),
    ('Artikel-Nr./Item No.',  5.0,  5.8),
    ('Qty',                  1.4,  1.5),
    ('Drawing No.',          2.5,  2.5),
    ('Bezeichnung',          7.4,  8.0),
    ('Full Name',   4.7,  5.2),
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
        self._hdr_fs.setRange(5, 18); self._hdr_fs.setValue(8); self._hdr_fs.setSuffix(" pt")
        self._hdr_fs.setFixedWidth(72)
        fl.addWidget(self._hdr_fs)
        fl.addSpacing(28)
        fl.addWidget(QLabel("Body:"))
        self._body_fs = QSpinBox()
        self._body_fs.setRange(5, 16); self._body_fs.setValue(7); self._body_fs.setSuffix(" pt")
        self._body_fs.setFixedWidth(72)
        fl.addWidget(self._body_fs)
        fl.addStretch()
        layout.addWidget(font_box)

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
        return {
            'header_font_size': self._hdr_fs.value(),
            'body_font_size':   self._body_fs.value(),
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
        self._export_fmt.addItems(["JSON", "Excel", "PDF"])
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
        """Export the current tree state — expanded = included, collapsed = header only."""
        if self._tree.invisibleRootItem().childCount() == 0:
            QMessageBox.information(self, "Export", "Load a BOM first.")
            return

        fmt  = self._export_fmt.currentText()
        data = self._build_export_data_from_tree()

        if fmt == "PDF":
            self._export_as_pdf(data)
            return

        ext_map    = {"JSON": ".json", "Excel": ".xlsx"}
        filter_map = {"JSON": "JSON Files (*.json)", "Excel": "Excel Files (*.xlsx)"}
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save BOM as {fmt}",
            f"BOM_{data['metadata']['item_no']}{ext_map[fmt]}",
            filter_map[fmt],
        )
        if not path:
            return

        try:
            if fmt == "JSON":
                self._save_as_json(data, path)
            elif fmt == "Excel":
                self._save_as_excel(data, path)
            self._status.setText(f"Saved {data['metadata']['total_items']} items → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            self._status.setText(f"Export error: {e}")

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

    def _widget_item_to_dict(self, item: QTreeWidgetItem,
                              is_root: bool = False):
        """
        Convert a QTreeWidgetItem into a dict for export.
        Returns None if the item is unchecked (skip from export).
        Children are included only if the item is expanded in the tree.
        """
        # Respect checkbox — unchecked item (and its children, which are also
        # unchecked by cascade) is excluded from the export entirely.
        if item.checkState(0) == Qt.CheckState.Unchecked:
            return None

        qty_text = item.text(2)
        try:
            qty = float(qty_text) if qty_text else ''
        except ValueError:
            qty = qty_text

        node = {
            'position':    '' if is_root else item.text(0),
            'item_no':     item.text(1),
            'qty':         qty,
            'scriptnum':   item.text(3),
            'has_bom':     item.data(0, _ROLE_HAS_BOM) or False,
            'description': item.text(4),
            'full_name':   item.text(5),
            'children':    [],
        }

        # Only recurse into children that have been loaded and the node is expanded
        if item.isExpanded():
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ROLE_ITEM_NO) == _PLACEHOLDER:
                    continue   # not yet loaded — skip
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

    def _flatten_bom(self, node: dict, level: int = 0) -> list:
        """Recursively flatten nested BOM dict into a list of row dicts.
        Rows with negative qty are excluded (along with their children).
        """
        qty = node.get('qty', '')
        if isinstance(qty, (int, float)) and qty < 0:
            return []

        indent = '  ' * level
        row = {
            'level':        level,
            'position':     str(node.get('position') or ''),
            'item_no':      indent + str(node.get('item_no') or ''),
            'qty':          qty,
            'scriptnum':    str(node.get('scriptnum') or ''),
            'description':  str(node.get('description') or ''),
            'full_name':    str(node.get('full_name') or ''),
            '_has_bom_raw': node.get('has_bom', False),
        }
        result = [row]
        for child in node.get('children', []):
            result.extend(self._flatten_bom(child, level + 1))
        return result

    def _save_as_excel(self, data: dict, path: str):
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

        meta = data.get('metadata', {})
        rows = self._flatten_bom(data.get('bom', {}))

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
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        )
        from reportlab.pdfgen.canvas import Canvas as _RLCanvas

        # ── Numbered canvas — "Page X von Y" at bottom-right ─────────
        class _NumberedCanvas(_RLCanvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states: list[dict] = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                n = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self._draw_page_number(n)
                    _RLCanvas.showPage(self)
                _RLCanvas.save(self)

            def _draw_page_number(self, total: int):
                self.saveState()
                self.setFont('Helvetica', 7)
                self.setFillColorRGB(0.4, 0.4, 0.4)
                self.drawRightString(
                    self._pagesize[0] - 1 * cm, 0.55 * cm,
                    f"{self._pageNumber} von {total}",
                )
                self.restoreState()

        # ── Defaults when called without a settings dialog ────────────
        if settings is None:
            settings = {'header_font_size': 8, 'body_font_size': 7, 'col_widths': None}

        hdr_fs  = settings.get('header_font_size', 8)
        body_fs = settings.get('body_font_size',   7)

        meta        = data.get('metadata', {})
        include_pos = self._chk_pdf_pos.isChecked()

        # ── Column layout — Level is never shown; Position is optional ──
        if include_pos:
            col_headers    = ['Position', 'Artikel-Nr./Item No.', 'Qty', 'Drawing No.', 'Bezeichnung', 'Full Name']
            default_widths = [2.0, 5.0, 1.4, 2.5, 7.4, 4.7]
        else:
            col_headers    = ['Artikel-Nr./Item No.', 'Qty', 'Drawing No.', 'Bezeichnung', 'Full Name']
            default_widths = [5.8, 1.5, 2.5, 8.0, 5.2]

        raw_widths = settings.get('col_widths') or default_widths
        col_widths = [w * cm for w in raw_widths]

        doc = SimpleDocTemplate(
            path,
            pagesize=landscape(A4),
            leftMargin=1*cm, rightMargin=1*cm,
            topMargin=1.5*cm, bottomMargin=1.5*cm,
        )
        styles = getSampleStyleSheet()
        story  = []

        title_style = ParagraphStyle(
            'BOMTitle', parent=styles['Heading2'], fontSize=11, spaceAfter=4,
        )
        story.append(Paragraph(
            f"BOM Export &mdash; {meta.get('item_no', '')} &nbsp;|&nbsp; "
            f"{meta.get('description', '')} &nbsp;|&nbsp; "
            f"Exported: {meta.get('exported_at', '')}",
            title_style,
        ))
        story.append(Spacer(1, 0.3*cm))

        rows = self._flatten_bom(data.get('bom', {}))

        # ── Paragraph styles — font/color live in the cell, not in TableStyle ──
        # This lets ReportLab wrap text and expand row height automatically.
        _lead = lambda fs: max(fs + 2, int(fs * 1.25))
        _hdr_ps  = ParagraphStyle('BOMHdr',  fontName='Helvetica-Bold',
                                  fontSize=hdr_fs,  leading=_lead(hdr_fs),
                                  textColor=colors.white, alignment=1)
        _norm_ps = ParagraphStyle('BOMCell', fontName='Helvetica',
                                  fontSize=body_fs, leading=_lead(body_fs))
        _bold_ps = ParagraphStyle('BOMCellB', fontName='Helvetica-Bold',
                                  fontSize=body_fs, leading=_lead(body_fs))

        def _p(text, style, indent_pt=0):
            txt = str(text) if text is not None else ''
            if indent_pt:
                s = ParagraphStyle('', parent=style, leftIndent=indent_pt)
                return Paragraph(txt.lstrip(), s)
            return Paragraph(txt, style)

        table_data = [[_p(h, _hdr_ps) for h in col_headers]]

        for row in rows:
            depth = row['level']
            st    = _bold_ps if depth == 0 else _norm_ps
            indent  = depth * 8   # 8 pt per nesting level
            qty_str = _fmt_qty(row['qty'])
            if include_pos:
                table_data.append([
                    _p(row['position'],    st),
                    _p(row['item_no'],     st, indent_pt=indent),
                    _p(qty_str,            st),
                    _p(row['scriptnum'],   st),
                    _p(row['description'], st),
                    _p(row['full_name'],   st),
                ])
            else:
                table_data.append([
                    _p(row['item_no'],     st, indent_pt=indent),
                    _p(qty_str,            st),
                    _p(row['scriptnum'],   st),
                    _p(row['description'], st),
                    _p(row['full_name'],   st),
                ])

        # FONTNAME/FONTSIZE/TEXTCOLOR removed — handled by Paragraph styles above
        style_cmds = [
            ('BACKGROUND',    (0, 0), (-1, 0),  colors.HexColor('#1565C0')),
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 3),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ]
        for i, row in enumerate(rows):
            depth   = row['level']
            hex_col = _DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)]
            style_cmds.append(('BACKGROUND', (0, i + 1), (-1, i + 1), colors.HexColor(hex_col)))

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

        doc.build(story, canvasmaker=_NumberedCanvas)

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
