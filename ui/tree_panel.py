from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont


class TableTreeWidget(QTreeWidget):
    """Left panel: shows Database → Module → Table hierarchy."""

    table_selected = pyqtSignal(str)  # emits table_name when user clicks a table

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("Database Tables")
        self.setMinimumWidth(220)
        self.setAnimated(True)
        self.itemClicked.connect(self._on_item_clicked)

    def populate(self, schema: dict):
        """Fill the tree from a {module: [(table_name, row_count), ...]} dict."""
        self.clear()

        bold = QFont()
        bold.setBold(True)

        for module in sorted(schema.keys()):
            tables = schema[module]

            module_item = QTreeWidgetItem(self)
            module_item.setText(0, f"{module}  ({len(tables)} tables)")
            module_item.setFont(0, bold)
            module_item.setData(0, Qt.ItemDataRole.UserRole, None)  # not a table
            module_item.setExpanded(False)

            for table_name, row_count in tables:
                child = QTreeWidgetItem(module_item)
                child.setText(0, f"{table_name}  [{row_count:,}]")
                child.setData(0, Qt.ItemDataRole.UserRole, table_name)

    def _on_item_clicked(self, item, column):
        table_name = item.data(0, Qt.ItemDataRole.UserRole)
        if table_name:
            self.table_selected.emit(table_name)
