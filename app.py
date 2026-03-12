import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from ui.main_window import MainWindow


def _light_palette() -> QPalette:
    """Explicit light palette — overrides Windows dark-mode system theme."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(0xF5, 0xF5, 0xF5))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(0x00, 0x00, 0x00))
    p.setColor(QPalette.ColorRole.Base,            QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(0xF0, 0xF0, 0xF0))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(0xFF, 0xFF, 0xDC))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(0x00, 0x00, 0x00))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(0x80, 0x80, 0x80))
    p.setColor(QPalette.ColorRole.Text,            QColor(0x00, 0x00, 0x00))
    p.setColor(QPalette.ColorRole.Button,          QColor(0xE8, 0xE8, 0xE8))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(0x00, 0x00, 0x00))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(0xFF, 0x00, 0x00))
    p.setColor(QPalette.ColorRole.Link,            QColor(0x00, 0x55, 0xCC))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(0x15, 0x65, 0xC0))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    # Disabled-state colours
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.WindowText,      QColor(0xA0, 0xA0, 0xA0))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.Text,            QColor(0xA0, 0xA0, 0xA0))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.ButtonText,      QColor(0xA0, 0xA0, 0xA0))
    return p


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BOM Explorer")
    # Fusion style ignores the Windows system theme (dark / light).
    # The explicit palette below locks every widget to white/light colours.
    app.setStyle('Fusion')
    app.setPalette(_light_palette())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
