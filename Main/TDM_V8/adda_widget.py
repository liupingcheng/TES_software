"""Clock, ADC, DAC, and FPGA configuration entry page."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt5.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionGroupBox,
    QVBoxLayout,
    QWidget,
)


MODULE_SPECS = (
    (
        "fpga",
        "FPGA算法板卡",
        (("clock_output", "时钟输出配置"), ("jesd", "JESD 配置")),
    ),
    (
        "ADC_readout",
        "DFB ADC板卡",
        (("adc_registers", "ADC板卡寄存器配置"),),
    ),
    (
        "FB_DAC",
        "DFB DAC板卡",
        (("dac_registers", "DAC板卡寄存器配置"),),
    ),
    (
        "gate_DAC",
        "选通 DAC板卡",
        (("dac_registers", "DAC板卡寄存器配置"),),
    ),
)


class SafeLineEdit(QLineEdit):
    """Require Enter to commit; Escape or focus loss restores the old value."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._committed_value = self.text()

    def set_committed_text(self, text):
        self._committed_value = str(text)
        self.setText(self._committed_value)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._committed_value = self.text()
        self.selectAll()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event)
            self._committed_value = self.text()
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.setText(self._committed_value)
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.setText(self._committed_value)
        super().focusOutEvent(event)


class BoardModuleCard(QGroupBox):
    """A board summary with mirrored network controls and config actions."""

    connection_params_changed = pyqtSignal(str, str, str, str)
    connect_requested = pyqtSignal(str)
    probe_requested = pyqtSignal(str)
    config_requested = pyqtSignal(str, str)

    def __init__(
        self,
        board_type,
        board_name,
        actions,
        ip="",
        port="24",
        local_ip="",
        parent=None,
    ):
        super().__init__(board_name, parent)
        content_font = QFont(self.font())
        title_font = QFont(content_font)
        network_font = QFont(content_font)
        if content_font.pointSizeF() > 0:
            title_font.setPointSizeF(content_font.pointSizeF() + 1.0)
            network_font.setPointSizeF(max(8.0, content_font.pointSizeF() - 1.0))
        elif content_font.pixelSize() > 0:
            title_font.setPixelSize(content_font.pixelSize() + 2)
            network_font.setPixelSize(max(10, content_font.pixelSize() - 1))
        title_font.setBold(True)
        network_font.setBold(False)
        self.setFont(title_font)
        self.setTitle(f"{board_name}          ")

        self.status_label = QLabel("未连接", self)
        self.status_label.setFont(network_font)
        self.status_label.setBackgroundRole(QPalette.Base)
        self.status_label.setAutoFillBackground(True)

        self.board_type = board_type
        self.board_name = board_name
        self.action_labels = dict(actions)
        self.config_buttons = {}

        self.setMinimumHeight(124)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(18, 0, 18, 10)
        card_layout.setSpacing(5)

        connection_layout = QHBoxLayout()
        connection_layout.setSpacing(6)

        ip_label = QLabel("IP Address:")
        connection_layout.addWidget(ip_label)
        self.ip_edit = SafeLineEdit(ip)
        self.ip_edit.setFixedWidth(128)
        connection_layout.addWidget(self.ip_edit)

        port_label = QLabel("Port:")
        connection_layout.addWidget(port_label)
        self.port_edit = SafeLineEdit(port)
        self.port_edit.setFixedWidth(52)
        self.port_edit.setAlignment(Qt.AlignCenter)
        connection_layout.addWidget(self.port_edit)

        local_ip_label = QLabel("Local IP:")
        connection_layout.addWidget(local_ip_label)
        self.local_ip_edit = SafeLineEdit(local_ip)
        self.local_ip_edit.setFixedWidth(128)
        connection_layout.addWidget(self.local_ip_edit)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setCursor(Qt.PointingHandCursor)
        self.connect_button.setMinimumWidth(76)
        self.connect_button.clicked.connect(
            lambda checked=False: self.connect_requested.emit(self.board_type)
        )
        connection_layout.addWidget(self.connect_button)

        self.probe_button = QPushButton("Test Link")
        self.probe_button.setCursor(Qt.PointingHandCursor)
        self.probe_button.setMinimumWidth(72)
        self.probe_button.clicked.connect(
            lambda checked=False: self.probe_requested.emit(self.board_type)
        )
        connection_layout.addWidget(self.probe_button)

        connection_layout.addStretch(1)

        for network_widget in (
            ip_label,
            self.ip_edit,
            port_label,
            self.port_edit,
            local_ip_label,
            self.local_ip_edit,
            self.connect_button,
            self.probe_button,
        ):
            network_widget.setFont(network_font)

        card_layout.addLayout(connection_layout)

        self.connection_separator = QFrame()
        self.connection_separator.setFrameShape(QFrame.HLine)
        self.connection_separator.setFrameShadow(QFrame.Sunken)
        card_layout.addWidget(self.connection_separator)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)
        action_layout.addStretch(1)

        for action_id, label in actions:
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(34)
            button.setMinimumWidth(222 if len(actions) == 1 else 168)
            button_font = QFont(content_font)
            button_font.setBold(True)
            button.setFont(button_font)
            button.clicked.connect(
                lambda checked=False, aid=action_id: self.config_requested.emit(
                    self.board_type, aid
                )
            )
            self.config_buttons[action_id] = button
            action_layout.addWidget(button)

        action_layout.addStretch(1)
        card_layout.addLayout(action_layout)

        for editor in (self.ip_edit, self.port_edit, self.local_ip_edit):
            editor.returnPressed.connect(self._emit_connection_params)

        self.update_connection_state(False)

    def _position_status_label(self):
        option = QStyleOptionGroupBox()
        self.initStyleOption(option)
        title_rect = self.style().subControlRect(
            QStyle.CC_GroupBox,
            option,
            QStyle.SC_GroupBoxLabel,
            self,
        )
        title_width = QFontMetrics(self.font()).horizontalAdvance(self.board_name)
        self.status_label.adjustSize()
        self.status_label.move(
            title_rect.x() + title_width + 6,
            title_rect.y()
            + max(0, (title_rect.height() - self.status_label.height()) // 2),
        )
        self.status_label.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_status_label()

    def _emit_connection_params(self):
        self.connection_params_changed.emit(
            self.board_type,
            self.ip_edit.text().strip(),
            self.port_edit.text().strip(),
            self.local_ip_edit.text().strip(),
        )

    def set_connection_params(self, ip, port, local_ip):
        editors_and_values = (
            (self.ip_edit, ip),
            (self.port_edit, port),
            (self.local_ip_edit, local_ip),
        )
        for editor, value in editors_and_values:
            editor.blockSignals(True)
            editor.set_committed_text(value)
            editor.blockSignals(False)

    def update_connection_state(self, is_connected):
        self.connect_button.setText("Disconnect" if is_connected else "Connect")
        self.status_label.setText("已连接" if is_connected else "未连接")
        status_palette = self.status_label.palette()
        status_color = QColor("#2ECC71" if is_connected else "#7F8C8D")
        status_palette.setColor(
            QPalette.WindowText,
            status_color,
        )
        status_palette.setColor(self.status_label.foregroundRole(), status_color)
        self.status_label.setPalette(status_palette)
        self._position_status_label()


class ADDAControlWidget(QWidget):
    """Four-board clock/AD/DA configuration entry page."""

    connection_params_changed = pyqtSignal(str, str, str, str)
    connect_requested = pyqtSignal(str)
    probe_requested = pyqtSignal(str)
    config_requested = pyqtSignal(str, str)

    def __init__(self, network_params=None, parent=None):
        super().__init__(parent)
        self.module_cards = {}
        network_params = network_params or {}

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(8, 8, 8, 8)
        page_layout.setSpacing(8)

        for board_type, board_name, actions in MODULE_SPECS:
            ip, port, local_ip = network_params.get(board_type, ("", "24", ""))
            card = BoardModuleCard(
                board_type,
                board_name,
                actions,
                ip,
                port,
                local_ip,
                self,
            )
            card.connection_params_changed.connect(
                self.connection_params_changed.emit
            )
            card.connect_requested.connect(self.connect_requested.emit)
            card.probe_requested.connect(self.probe_requested.emit)
            card.config_requested.connect(self.config_requested.emit)
            self.module_cards[board_type] = card
            page_layout.addWidget(card)

        page_layout.addStretch(1)

    def set_connection_params(self, board_type, ip, port, local_ip):
        card = self.module_cards.get(board_type)
        if card is not None:
            card.set_connection_params(ip, port, local_ip)

    def update_connection_state(self, board_type, is_connected):
        card = self.module_cards.get(board_type)
        if card is not None:
            card.update_connection_state(is_connected)

    def action_description(self, board_type, action_id):
        card = self.module_cards.get(board_type)
        if card is None:
            return board_type, action_id
        return card.board_name, card.action_labels.get(action_id, action_id)
