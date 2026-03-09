import csv
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QTabWidget, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt

from db.schema_loader import SchemaLoader
from db.table_loader  import TableLoader
from ui.tree_panel    import TableTreeWidget
from ui.data_panel    import DataPanel
from ui.detail_panel  import DetailPanel
from ui.bom_panel     import BOMPanel
from ui.search_panel  import SearchPanel
from ui.stock_panel   import StockPanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BOM Explorer — XALinl")
        self.resize(1400, 820)

        self._current_table = None
        self._schema_loader = None
        self._table_loader  = None

        self._setup_ui()
        self._setup_menu()
        self._load_schema()

    # ------------------------------------------------------------------ UI setup
    def _setup_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # --- Tab 1: Table Explorer ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._tree   = TableTreeWidget()
        self._data   = DataPanel()
        self._detail = DetailPanel()
        splitter.addWidget(self._tree)
        splitter.addWidget(self._data)
        splitter.addWidget(self._detail)
        splitter.setSizes([240, 840, 320])
        tabs.addTab(splitter, "Table Explorer")

        # --- Tab 2: BOM Tree ---
        self._bom_panel = BOMPanel()
        tabs.addTab(self._bom_panel, "BOM Tree")

        # --- Tab 3: Search Space! ---
        self._search_panel = SearchPanel()
        tabs.addTab(self._search_panel, "Compare BOM")

        # --- Tab 4: Stocks ---
        # Pass bom_panel so "Open BOM" button can load directly into Tab 2
        self._stock_panel = StockPanel(bom_panel=self._bom_panel)
        tabs.addTab(self._stock_panel, "Stocks")

        # Wire Table Explorer signals
        self._tree.table_selected.connect(self._on_table_selected)
        self._data.page_changed.connect(self._on_page_changed)
        self._data.dataset_changed.connect(self._on_dataset_changed)
        self._data.row_selected.connect(self._detail.populate)

        self.statusBar().showMessage("Connecting to DEBLNSVERP01 ...")

    def _setup_menu(self):
        file_menu = self.menuBar().addMenu("File")

        export_act = file_menu.addAction("Export current page to CSV...")
        export_act.triggered.connect(self._export_csv)

        file_menu.addSeparator()

        quit_act = file_menu.addAction("Quit")
        quit_act.triggered.connect(self.close)

    # ------------------------------------------------------------------ schema
    def _load_schema(self):
        self._schema_loader = SchemaLoader()
        self._schema_loader.schema_ready.connect(self._on_schema_ready)
        self._schema_loader.error.connect(self._on_error)
        self._schema_loader.start()

    def _on_schema_ready(self, schema: dict):
        self._tree.populate(schema)
        total = sum(len(v) for v in schema.values())
        self.statusBar().showMessage(
            f"Connected  |  {total} tables across {len(schema)} modules  |  Select a table to browse"
        )

    # ------------------------------------------------------------------ table loading
    def _on_table_selected(self, table_name: str):
        self._current_table = table_name
        self._data.reset_page()
        self._detail._clear()
        self._start_loader(table_name, page=0, load_count=True)

    def _on_page_changed(self, page: int, dataset: str):
        if self._current_table:
            self._start_loader(self._current_table, page=page, load_count=False)

    def _on_dataset_changed(self, dataset: str):
        if self._current_table:
            self._start_loader(self._current_table, page=0, load_count=True)

    def _start_loader(self, table_name: str, page: int, load_count: bool):
        # Stop any running loader gracefully
        if self._table_loader and self._table_loader.isRunning():
            self._table_loader.quit()
            self._table_loader.wait()

        self.statusBar().showMessage(f"Loading  {table_name}  ...")

        self._table_loader = TableLoader(
            table_name=table_name,
            dataset=self._data.get_dataset(),
            page=page,
            page_size=DataPanel.PAGE_SIZE,
            load_count=load_count,
        )
        self._table_loader.count_ready.connect(self._data.set_total_rows)
        self._table_loader.data_ready.connect(self._on_data_ready)
        self._table_loader.error.connect(self._on_error)
        self._table_loader.start()

    def _on_data_ready(self, rows: list, columns: list):
        self._data.populate(rows, columns)
        self.statusBar().showMessage(
            f"Table: {self._current_table}  |  "
            f"Dataset: {self._data.get_dataset()}  |  "
            f"Showing {len(rows)} rows on this page"
        )

    # ------------------------------------------------------------------ export
    def _export_csv(self):
        if not self._current_table:
            QMessageBox.information(self, "Export", "Select a table first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV",
            f"{self._current_table}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return

        model = self._data._model
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = [
                model.horizontalHeaderItem(c).text()
                for c in range(model.columnCount())
            ]
            writer.writerow(headers)
            for r in range(model.rowCount()):
                writer.writerow([
                    model.item(r, c).text()
                    for c in range(model.columnCount())
                ])

        self.statusBar().showMessage(f"Exported {model.rowCount()} rows → {path}")

    # ------------------------------------------------------------------ error
    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Database Error", msg)
