from PyQt6.QtWidgets import QMainWindow, QTabWidget, QMessageBox

from ui.bom_panel    import BOMPanel
from ui.search_panel import SearchPanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BOM Explorer — XALinl")
        self.resize(1400, 820)

        self._setup_ui()

    # ------------------------------------------------------------------ UI setup
    def _setup_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # --- Tab 1: BOM Tree ---
        self._bom_panel = BOMPanel()
        tabs.addTab(self._bom_panel, "BOM Tree")

        # --- Tab 2: Compare BOM ---
        self._search_panel = SearchPanel()
        tabs.addTab(self._search_panel, "Compare BOM")

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------ error
    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)
