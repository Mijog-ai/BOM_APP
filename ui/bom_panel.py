import json
import decimal
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from db.bom_loader import BOMLoader


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
        self._export_fmt.setFixedWidth(65)
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
            "Checked  → hide rows where ScriptNum + ItemNo appear more than once\n"
            "Unchecked → show every raw row returned by the query"
        )

        top.addWidget(QLabel("Item No:"))
        top.addWidget(self._item_input, 1)
        top.addWidget(QLabel("Dataset:"))
        top.addWidget(self._dataset_cb)
        top.addWidget(self._btn_load)
        top.addWidget(self._btn_clear)
        top.addWidget(self._chk_unique)
        top.addWidget(self._export_fmt)
        top.addWidget(self._btn_export)
        layout.addLayout(top)

        # --- Status ---
        self._status = QLabel("Enter an item number and click Load BOM.")
        layout.addWidget(self._status)

        # --- Tree ---
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

        # ── Deduplicate by (ScriptNum, ItemNo) if checkbox is checked ──
        if self._chk_unique.isChecked():
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
                pos=str(row.get('ScriptNum')   or ''),
                item_no=str(row.get('ItemNo')  or ''),
                qty=str(row.get('Qty')         or ''),
                has_bom=has_bom,
                description=str(row.get('Description') or ''),
                full_name=str(row.get('FullName')       or ''),
            )

            if has_bom:
                for col in range(self._tree.columnCount()):
                    child.setForeground(col, QColor('#1565C0'))  # blue

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
        total = data['metadata']['total_items']

        ext_map    = {"JSON": ".json",  "Excel": ".xlsx",  "PDF": ".pdf"}
        filter_map = {
            "JSON":  "JSON Files (*.json)",
            "Excel": "Excel Files (*.xlsx)",
            "PDF":   "PDF Files (*.pdf)",
        }
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
            elif fmt == "PDF":
                self._save_as_pdf(data, path)
            self._status.setText(f"Saved {total} items → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            self._status.setText(f"Export error: {e}")

    # ------------------------------------------------------------------ tree → data
    def _build_export_data_from_tree(self) -> dict:
        """Read the current QTreeWidget and build the export data dict."""
        root_qt = self._tree.invisibleRootItem().child(0)
        bom     = self._widget_item_to_dict(root_qt, is_root=True) if root_qt else {}
        total   = self._count_nodes(bom)
        return {
            'metadata': {
                'item_no':     self._item_input.text().strip(),
                'dataset':     self._dataset_cb.currentText(),
                'exported_at': datetime.now().isoformat(timespec='seconds'),
                'total_items': total,
            },
            'bom': bom,
        }

    def _widget_item_to_dict(self, item: QTreeWidgetItem,
                              is_root: bool = False) -> dict:
        """
        Convert a QTreeWidgetItem into a dict for export.
        Children are included only if the item is expanded in the tree.
        """
        qty_text = item.text(2)
        try:
            qty = float(qty_text) if qty_text else ''
        except ValueError:
            qty = qty_text

        node = {
            'script_num':  '' if is_root else item.text(0),
            'item_no':     item.text(1),
            'qty':         qty,
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
                node['children'].append(self._widget_item_to_dict(child))

        return node

    def _count_nodes(self, node: dict) -> int:
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
            'script_num':   str(node.get('script_num') or ''),
            'item_no':      indent + str(node.get('item_no') or ''),
            'qty':          qty,
            'has_bom':      'Yes' if (node.get('has_bom') or node.get('children')) else 'No',
            'description':  str(node.get('description') or ''),
            'full_name':    str(node.get('full_name') or ''),
            '_has_bom_raw': node.get('has_bom', False),
        }
        result = [row]
        for child in node.get('children', []):
            result.extend(self._flatten_bom(child, level + 1))
        return result

    def _save_as_excel(self, data: dict, path: str):
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb   = openpyxl.Workbook()
        meta = data.get('metadata', {})

        # ── Sheet 1: BOM Tree ──
        ws = wb.active
        ws.title = 'BOM Tree'

        title = (
            f"BOM Export — {meta.get('item_no', '')}  |  "
            f"Dataset: {meta.get('dataset', '')}  |  "
            f"Items: {meta.get('total_items', '')}  |  "
            f"Exported: {meta.get('exported_at', '')}"
        )
        ws['A1'] = title
        ws['A1'].font = Font(bold=True, size=11)
        ws.merge_cells('A1:G1')
        ws.append([])  # blank spacer row

        headers = ['Level', 'ScriptNum', 'Item No', 'Qty', 'Has BOM', 'Description', 'Full Name']
        ws.append(headers)
        header_fill = PatternFill(fill_type='solid', fgColor='1565C0')
        header_font = Font(bold=True, color='FFFFFF')
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

        ws.freeze_panes = 'A4'

        rows = self._flatten_bom(data.get('bom', {}))
        alt_fill    = PatternFill(fill_type='solid', fgColor='EEF2FF')
        blue_font   = Font(color='1565C0')
        normal_font = Font()

        for i, row in enumerate(rows):
            ws.append([
                row['level'], row['script_num'], row['item_no'],
                row['qty'],   row['has_bom'],    row['description'], row['full_name'],
            ])
            excel_row = i + 4
            bg = alt_fill if i % 2 == 1 else None
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=excel_row, column=col)
                cell.font = blue_font if (row['_has_bom_raw'] and row['level'] > 0) else normal_font
                if bg:
                    cell.fill = bg

        col_widths = [8, 12, 30, 8, 10, 38, 45]
        for col_idx, width in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # ── Sheet 2: Metadata ──
        ws2 = wb.create_sheet('Metadata')
        ws2.append(['Field', 'Value'])
        ws2['A1'].font = Font(bold=True)
        ws2['B1'].font = Font(bold=True)
        for key, val in meta.items():
            ws2.append([key, str(val)])
        ws2.column_dimensions['A'].width = 20
        ws2.column_dimensions['B'].width = 35

        wb.save(path)

    def _save_as_pdf(self, data: dict, path: str):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        )

        meta = data.get('metadata', {})
        doc  = SimpleDocTemplate(
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
            f"Dataset: {meta.get('dataset', '')} &nbsp;|&nbsp; "
            f"Items: {meta.get('total_items', '')} &nbsp;|&nbsp; "
            f"Exported: {meta.get('exported_at', '')}",
            title_style,
        ))
        story.append(Spacer(1, 0.3*cm))

        rows = self._flatten_bom(data.get('bom', {}))

        col_headers = ['Lvl', 'ScriptNum', 'Item No', 'Qty', 'BOM?', 'Description', 'Full Name']
        table_data  = [col_headers]
        blue_rows   = []

        for i, row in enumerate(rows, start=1):
            table_data.append([
                str(row['level']),
                row['script_num'],
                row['item_no'],
                str(row['qty']) if row['qty'] != '' else '',
                row['has_bom'],
                row['description'][:65],
                row['full_name'][:52],
            ])
            if row['_has_bom_raw'] and row['level'] > 0:
                blue_rows.append(i)

        style_cmds = [
            ('BACKGROUND',    (0, 0), (-1, 0),  colors.HexColor('#1565C0')),
            ('TEXTCOLOR',     (0, 0), (-1, 0),  colors.white),
            ('FONTNAME',      (0, 0), (-1, 0),  'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0),  8),
            ('ALIGN',         (0, 0), (-1, 0),  'CENTER'),
            ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',      (0, 1), (-1, -1), 7),
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#CCCCCC')),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]
        for i in range(1, len(table_data)):
            bg = colors.HexColor('#EEF2FF') if i % 2 == 0 else colors.white
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), bg))
        for i in blue_rows:
            style_cmds.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#1565C0')))

        col_widths = [0.8*cm, 2*cm, 4.8*cm, 1.3*cm, 1.3*cm, 7*cm, 5.8*cm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

        doc.build(story)

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

        if has_bom:
            ph = QTreeWidgetItem(node)
            ph.setText(1, '...')
            ph.setData(0, _ROLE_ITEM_NO, _PLACEHOLDER)

        return node
