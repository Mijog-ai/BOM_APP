from PyQt6.QtWidgets import QScrollArea, QWidget, QFormLayout, QLabel
from PyQt6.QtCore import Qt


class DetailPanel(QScrollArea):
    """Right panel: shows all field:value pairs for the selected row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(240)

        self._container = QWidget()
        self._layout    = QFormLayout(self._container)
        self._layout.setLabelAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.setWidget(self._container)

    def populate(self, row_data: list, columns: list):
        self._clear()
        for col, val in zip(columns, row_data):
            key_label = QLabel(col)
            key_label.setStyleSheet("font-weight: bold; color: #555;")
            key_label.setAlignment(Qt.AlignmentFlag.AlignTop)

            val_label = QLabel(str(val) if val else '—')
            val_label.setWordWrap(True)
            val_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self._layout.addRow(key_label, val_label)

    def _clear(self):
        while self._layout.rowCount():
            self._layout.removeRow(0)
