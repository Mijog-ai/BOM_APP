from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTableView, QLineEdit, QComboBox,
    QPushButton, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem


class DataPanel(QWidget):
    """Center panel: search bar, data table, pagination controls."""

    page_changed    = pyqtSignal(int, str)    # (new_page, dataset)
    dataset_changed = pyqtSignal(str)          # new dataset value
    row_selected    = pyqtSignal(list, list)   # (row_data, column_names)

    PAGE_SIZE = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns    = []
        self._total_rows = 0
        self._page       = 0
        self._setup_ui()

    # ------------------------------------------------------------------ setup
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Top bar: search + dataset selector
        top = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search in current page...")
        self._dataset_cb = QComboBox()
        self._dataset_cb.addItems(['INL', 'KON'])
        top.addWidget(QLabel("Filter:"))
        top.addWidget(self._search, 1)
        top.addWidget(QLabel("Dataset:"))
        top.addWidget(self._dataset_cb)
        layout.addLayout(top)

        # Table view
        self._model = QStandardItemModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search all columns

        self._view = QTableView()
        self._view.setModel(self._proxy)
        self._view.setAlternatingRowColors(True)
        self._view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._view.setSortingEnabled(True)
        self._view.horizontalHeader().setStretchLastSection(True)
        self._view.verticalHeader().setDefaultSectionSize(22)
        layout.addWidget(self._view)

        # Bottom bar: pagination
        bottom = QHBoxLayout()
        self._btn_prev   = QPushButton("◀ Prev")
        self._btn_next   = QPushButton("Next ▶")
        self._page_label = QLabel("No table selected")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_prev.setFixedWidth(80)
        self._btn_next.setFixedWidth(80)
        bottom.addWidget(self._btn_prev)
        bottom.addWidget(self._page_label, 1)
        bottom.addWidget(self._btn_next)
        layout.addLayout(bottom)

        # Connections
        self._search.textChanged.connect(self._proxy.setFilterFixedString)
        self._btn_prev.clicked.connect(self._prev_page)
        self._btn_next.clicked.connect(self._next_page)
        self._dataset_cb.currentTextChanged.connect(self._on_dataset_changed)
        self._view.selectionModel().currentRowChanged.connect(self._on_row_changed)

    # ------------------------------------------------------------------ public API
    def get_dataset(self) -> str:
        return self._dataset_cb.currentText()

    def reset_page(self):
        self._page = 0
        self._total_rows = 0

    def set_total_rows(self, total: int):
        self._total_rows = total
        self._update_pagination()

    def populate(self, rows: list, columns: list):
        self._columns = columns
        self._model.clear()
        self._model.setHorizontalHeaderLabels(columns)

        for row_data in rows:
            items = []
            for v in row_data:
                item = QStandardItem(str(v) if v is not None else '')
                item.setEditable(False)
                items.append(item)
            self._model.appendRow(items)

        self._view.resizeColumnsToContents()
        self._update_pagination()

    # ------------------------------------------------------------------ internal
    def _update_pagination(self):
        total_pages = max(1, -(-self._total_rows // self.PAGE_SIZE))  # ceiling div
        self._page_label.setText(
            f"Page {self._page + 1} / {total_pages}   ({self._total_rows:,} rows)"
        )
        self._btn_prev.setEnabled(self._page > 0)
        self._btn_next.setEnabled((self._page + 1) * self.PAGE_SIZE < self._total_rows)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.page_changed.emit(self._page, self.get_dataset())

    def _next_page(self):
        if (self._page + 1) * self.PAGE_SIZE < self._total_rows:
            self._page += 1
            self.page_changed.emit(self._page, self.get_dataset())

    def _on_dataset_changed(self, dataset: str):
        self._page = 0
        self.dataset_changed.emit(dataset)

    def _on_row_changed(self, current, previous):
        if not current.isValid() or not self._columns:
            return
        source_idx = self._proxy.mapToSource(current)
        row = source_idx.row()
        if row < 0:
            return
        row_data = [
            self._model.item(row, col).text()
            for col in range(self._model.columnCount())
        ]
        self.row_selected.emit(row_data, self._columns)
