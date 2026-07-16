import os
import sys
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QPalette
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from adda_widget import ADDAControlWidget
from TDM_software import MainWindow


class ADDAWidgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def make_widget(self):
        network_params = {
            "fpga": ("192.168.200.1", "24", "192.168.200.2"),
            "ADC_readout": ("192.168.104.1", "24", "192.168.104.2"),
            "FB_DAC": ("192.168.105.1", "24", "192.168.105.2"),
            "gate_DAC": ("192.168.106.1", "24", "192.168.106.2"),
        }
        widget = ADDAControlWidget(network_params)
        self.widgets.append(widget)
        return widget

    def make_window(self, settings_path=None):
        settings_path = settings_path or os.path.join(
            self.temp_dir.name, "tdm-adda.ini"
        )
        window = MainWindow(QSettings(settings_path, QSettings.IniFormat))
        self.widgets.append(window)
        return window

    def test_four_modules_and_five_config_actions(self):
        widget = self.make_widget()

        self.assertEqual(
            list(widget.module_cards),
            ["fpga", "ADC_readout", "FB_DAC", "gate_DAC"],
        )
        self.assertEqual(
            [card.board_name for card in widget.module_cards.values()],
            ["FPGA算法板卡", "DFB ADC板卡", "DFB DAC板卡", "选通 DAC板卡"],
        )
        self.assertEqual(
            sum(len(card.config_buttons) for card in widget.module_cards.values()),
            5,
        )
        for card in widget.module_cards.values():
            self.assertGreater(card.font().pointSizeF(), card.ip_edit.font().pointSizeF())
            self.assertTrue(card.font().bold())
            self.assertFalse(card.ip_edit.font().bold())

        config_spy = QSignalSpy(widget.config_requested)
        for card in widget.module_cards.values():
            for button in card.config_buttons.values():
                button.click()

        self.assertEqual(
            [list(call) for call in config_spy],
            [
                ["fpga", "clock_output"],
                ["fpga", "jesd"],
                ["ADC_readout", "adc_registers"],
                ["FB_DAC", "dac_registers"],
                ["gate_DAC", "dac_registers"],
            ],
        )

    def test_safe_editing_and_request_board_ids(self):
        widget = self.make_widget()
        widget.show()
        QApplication.setActiveWindow(widget)
        self.app.processEvents()
        card = widget.module_cards["fpga"]

        params_spy = QSignalSpy(widget.connection_params_changed)
        card.ip_edit.setFocus()
        self.app.processEvents()
        card.ip_edit.setText("10.8.0.1")
        QTest.keyClick(card.ip_edit, Qt.Key_Return)
        self.assertEqual(
            list(params_spy[0]),
            ["fpga", "10.8.0.1", "24", "192.168.200.2"],
        )

        card.ip_edit.setFocus()
        self.app.processEvents()
        card.ip_edit.setText("discard-with-escape")
        QTest.keyClick(card.ip_edit, Qt.Key_Escape)
        self.assertEqual(card.ip_edit.text(), "10.8.0.1")

        card.ip_edit.setFocus()
        self.app.processEvents()
        card.ip_edit.setText("discard-on-blur")
        card.connect_button.setFocus()
        self.app.processEvents()
        self.assertEqual(card.ip_edit.text(), "10.8.0.1")
        self.assertEqual(len(params_spy), 1)

        connect_spy = QSignalSpy(widget.connect_requested)
        probe_spy = QSignalSpy(widget.probe_requested)
        widget.module_cards["FB_DAC"].connect_button.click()
        widget.module_cards["gate_DAC"].probe_button.click()
        self.assertEqual(list(connect_spy[0]), ["FB_DAC"])
        self.assertEqual(list(probe_spy[0]), ["gate_DAC"])

    def test_main_window_two_way_sync_and_connection_state(self):
        window = self.make_window()
        window.show()
        QApplication.setActiveWindow(window)
        self.app.processEvents()
        card = window.adda_widget.module_cards["ADC_readout"]

        card.ip_edit.setFocus()
        self.app.processEvents()
        card.ip_edit.setText("10.40.0.1")
        QTest.keyClick(card.ip_edit, Qt.Key_Return)
        self.assertEqual(window.board_ip_edits["ADC_readout"].text(), "10.40.0.1")

        local_ip_edit = window.board_local_ip_edits["ADC_readout"]
        local_ip_edit.setFocus()
        self.app.processEvents()
        local_ip_edit.setText("10.40.0.2")
        QTest.keyClick(local_ip_edit, Qt.Key_Return)
        self.assertEqual(card.local_ip_edit.text(), "10.40.0.2")

        window.on_board_connected("ADC_readout")
        self.assertEqual(window.board_connection_btns["ADC_readout"].text(), "Disconnect")
        self.assertEqual(card.connect_button.text(), "Disconnect")
        self.assertEqual(card.status_label.text(), "已连接")
        self.assertEqual(
            card.status_label.palette().color(QPalette.WindowText).name(),
            "#2ecc71",
        )

        window.on_board_disconnected("ADC_readout", "test disconnect")
        self.assertEqual(window.board_connection_btns["ADC_readout"].text(), "Connect")
        self.assertEqual(card.connect_button.text(), "Connect")
        self.assertEqual(card.status_label.text(), "未连接")
        self.assertEqual(
            card.status_label.palette().color(QPalette.WindowText).name(),
            "#7f8c8d",
        )

    def test_cache_restore_and_placeholder_actions_do_not_send(self):
        settings_path = os.path.join(self.temp_dir.name, "shared.ini")
        first = self.make_window(settings_path)
        first.board_ip_edits["fpga"].setText("10.50.0.1")
        first.board_port_edits["fpga"].setText("5024")
        first.board_local_ip_edits["fpga"].setText("10.50.0.2")
        self.assertTrue(first.save_session_cache())

        second = self.make_window(settings_path)
        fpga_card = second.adda_widget.module_cards["fpga"]
        self.assertEqual(fpga_card.ip_edit.text(), "10.50.0.1")
        self.assertEqual(fpga_card.port_edit.text(), "5024")
        self.assertEqual(fpga_card.local_ip_edit.text(), "10.50.0.2")

        with patch.object(second.tcp_manager, "send_data") as send_data:
            for card in second.adda_widget.module_cards.values():
                for button in card.config_buttons.values():
                    button.click()
            send_data.assert_not_called()

        self.assertEqual(
            second.connection_log.toPlainText().count("功能待接入，本次未下发数据"),
            5,
        )


if __name__ == "__main__":
    unittest.main()
