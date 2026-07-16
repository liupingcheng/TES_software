"""Empty clock/AD/DA configuration page, reserved for a new implementation."""

from PyQt5.QtWidgets import QWidget


class ADDAControlWidget(QWidget):
    """Blank container for the clock/AD/DA configuration page."""

    def __init__(self, parent=None):
        super().__init__(parent)
