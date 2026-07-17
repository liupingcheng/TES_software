import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
V8_DIRECTORY = Path(__file__).resolve().parents[1] / "TDM_V8"
sys.path.insert(0, str(V8_DIRECTORY))

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QDesktopServices, QPalette
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication, QMessageBox

from adda_widget import ADDAControlWidget
from TDM_software import (
    ADDA_CONFIG_DIRECTORY,
    MainWindow,
    build_fixed_light_palette,
)


class ADDAWidgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        with patch.object(QMessageBox, "warning"):
            for widget in self.widgets:
                if hasattr(widget, "adda_config_sender"):
                    widget.adda_config_sender.cancel_all("test cleanup")
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

    def test_four_modules_and_config_actions(self):
        widget = self.make_widget()

        self.assertEqual(
            list(widget.module_cards),
            ["ADC_readout", "FB_DAC", "gate_DAC", "fpga"],
        )
        self.assertEqual(
            [card.board_name for card in widget.module_cards.values()],
            ["DFB ADC板卡", "DFB DAC板卡", "选通 DAC板卡", "FPGA算法板卡"],
        )
        self.assertEqual(
            sum(len(card.config_buttons) for card in widget.module_cards.values()),
            5,
        )
        self.assertEqual(
            [
                list(card.file_action_labels.values())
                for card in widget.module_cards.values()
            ],
            [
                ["ADC 配置文件"],
                ["DAC 配置文件"],
                ["DAC 配置文件"],
                ["时钟配置文件", "JESD 配置文件"],
            ],
        )
        self.assertEqual(
            sum(
                len(card.config_file_buttons)
                for card in widget.module_cards.values()
            ),
            5,
        )
        for card in widget.module_cards.values():
            self.assertGreater(card.font().pointSizeF(), card.ip_edit.font().pointSizeF())
            self.assertTrue(card.font().bold())
            self.assertFalse(card.ip_edit.font().bold())
            for button in card.config_buttons.values():
                self.assertFalse(button.font().bold())
            for button in card.config_file_buttons.values():
                self.assertFalse(button.font().bold())

        config_spy = QSignalSpy(widget.config_requested)
        for card in widget.module_cards.values():
            for button in card.config_buttons.values():
                button.click()

        self.assertEqual(
            [list(call) for call in config_spy],
            [
                ["ADC_readout", "adc_registers"],
                ["FB_DAC", "dac_registers"],
                ["gate_DAC", "dac_registers"],
                ["fpga", "clock_output"],
                ["fpga", "jesd"],
            ],
        )

        file_spy = QSignalSpy(widget.config_file_requested)
        for card in widget.module_cards.values():
            for button in card.config_file_buttons.values():
                button.click()

        self.assertEqual(
            [list(call) for call in file_spy],
            [
                ["ADC_readout", "adc"],
                ["FB_DAC", "dac"],
                ["gate_DAC", "dac"],
                ["fpga", "clock"],
                ["fpga", "jesd"],
            ],
        )

    def test_bundled_configuration_files(self):
        reference_directory = Path(__file__).resolve().parents[2] / "ref" / "AD_DA_SPI_config"
        copied_files = (
            "adc_configuration.txt",
            "dac39j84_0_1_2_configuration.txt",
            "control_lmk_configuration.txt",
        )
        for file_name in copied_files:
            self.assertEqual(
                (ADDA_CONFIG_DIRECTORY / file_name).read_bytes(),
                (reference_directory / file_name).read_bytes(),
            )
        self.assertEqual(
            (ADDA_CONFIG_DIRECTORY / "JESD_configuration.txt").read_bytes(),
            b"",
        )

    def test_fixed_light_palette_does_not_inherit_dark_system_colors(self):
        palette = build_fixed_light_palette()
        self.assertEqual(palette.color(QPalette.Window).name(), "#f0f0f0")
        self.assertEqual(palette.color(QPalette.WindowText).name(), "#202124")
        self.assertEqual(palette.color(QPalette.Base).name(), "#ffffff")
        self.assertEqual(palette.color(QPalette.Text).name(), "#202124")
        self.assertEqual(palette.color(QPalette.Button).name(), "#f2f2f2")
        self.assertEqual(palette.color(QPalette.ButtonText).name(), "#202124")
        self.assertEqual(palette.color(QPalette.Highlight).name(), "#2a82da")

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

    def test_cache_restore_and_unconnected_actions_do_not_send(self):
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

        with patch.object(second.tcp_manager, "send_data") as send_data, patch.object(
            QMessageBox, "warning"
        ) as warning:
            for card in second.adda_widget.module_cards.values():
                for button in card.config_buttons.values():
                    button.click()
            send_data.assert_not_called()

        self.assertEqual(
            second.connection_log.toPlainText().count("板卡未连接"),
            5,
        )
        self.assertEqual(warning.call_count, 5)

    def test_all_config_actions_send_mapped_payloads_and_restore_ui(self):
        window = self.make_window()
        config_directory = Path(self.temp_dir.name) / "runtime-configs"
        config_directory.mkdir()
        contents = {
            "adc_configuration.txt": "01020304\n",
            "dac39j84_0_1_2_configuration.txt": "AABBCCDD\n",
            "control_lmk_configuration.txt": "11223344\n",
            "JESD_configuration.txt": "1000000800000001\n",
        }
        for file_name, text in contents.items():
            (config_directory / file_name).write_text(text, encoding="utf-8")

        window.adda_config_sender.command_delay_ms = 0
        window.adda_config_sender.wait_marker_delay_ms = 0
        window.adda_config_sender.reply_timeout_ms = 100
        actions = (
            ("ADC_readout", "adc_registers", b"\x01\x02\x03\x04"),
            ("FB_DAC", "dac_registers", b"\xAA\xBB\xCC\xDD"),
            ("gate_DAC", "dac_registers", b"\xAA\xBB\xCC\xDD"),
            ("fpga", "clock_output", b"\x11\x22\x33\x44"),
            (
                "fpga",
                "jesd",
                b"\x10\x00\x00\x08\x00\x00\x00\x01",
            ),
        )

        with patch(
            "TDM_software.ADDA_CONFIG_DIRECTORY", config_directory
        ), patch.object(
            window.tcp_manager, "is_connected", return_value=True
        ), patch.object(
            window.tcp_manager, "send_data", return_value=True
        ) as send_data, patch.object(
            QMessageBox, "warning"
        ) as warning:
            for board_type, action_id, expected_payload in actions:
                card = window.adda_widget.module_cards[board_type]
                button = card.config_buttons[action_id]
                button.click()
                self.app.processEvents()
                QTest.qWait(5)

                self.assertFalse(button.isEnabled())
                self.assertEqual(button.text(), "配置中 0/1")
                self.assertEqual(
                    send_data.call_args_list[-1].args,
                    (board_type, expected_payload),
                )

                window.on_board_data_received(board_type, 4, b"ACK!")
                self.app.processEvents()
                self.assertTrue(button.isEnabled())
                self.assertEqual(button.text(), card.action_labels[action_id])

        self.assertEqual(send_data.call_count, 5)
        warning.assert_not_called()
        self.assertNotIn("收到", window.connection_log.toPlainText())
        self.assertEqual(
            window.connection_log.toPlainText().count("配置成功"),
            5,
        )

    def test_empty_jesd_and_reply_timeout_report_errors_without_stuck_ui(self):
        window = self.make_window()
        config_directory = Path(self.temp_dir.name) / "error-configs"
        config_directory.mkdir()
        (config_directory / "JESD_configuration.txt").write_text(
            "",
            encoding="utf-8",
        )
        (config_directory / "adc_configuration.txt").write_text(
            "01020304\n",
            encoding="utf-8",
        )
        window.adda_config_sender.command_delay_ms = 0
        window.adda_config_sender.reply_timeout_ms = 20

        jesd_button = window.adda_widget.module_cards["fpga"].config_buttons[
            "jesd"
        ]
        adc_button = window.adda_widget.module_cards["ADC_readout"].config_buttons[
            "adc_registers"
        ]
        with patch(
            "TDM_software.ADDA_CONFIG_DIRECTORY", config_directory
        ), patch.object(
            window.tcp_manager, "is_connected", return_value=True
        ), patch.object(
            window.tcp_manager, "send_data", return_value=True
        ) as send_data, patch.object(
            QMessageBox, "warning"
        ) as warning:
            jesd_button.click()
            self.assertEqual(send_data.call_count, 0)
            self.assertTrue(jesd_button.isEnabled())
            self.assertIn("配置文件为空", window.connection_log.toPlainText())

            finished = QSignalSpy(window.adda_config_sender.finished)
            adc_button.click()
            self.assertTrue(finished.wait(500))
            self.assertEqual(send_data.call_count, 1)
            self.assertTrue(adc_button.isEnabled())
            self.assertEqual(adc_button.text(), "ADC板卡寄存器配置")
            self.assertIn("等待 4 字节回复超时", window.connection_log.toPlainText())

        self.assertEqual(warning.call_count, 2)

    def test_configuration_file_buttons_open_expected_files_without_sending(self):
        window = self.make_window()
        with patch.object(
            QDesktopServices, "openUrl", return_value=True
        ) as open_url, patch.object(window.tcp_manager, "send_data") as send_data:
            for card in window.adda_widget.module_cards.values():
                for button in card.config_file_buttons.values():
                    button.click()

        opened_file_names = [
            Path(call.args[0].toLocalFile()).name
            for call in open_url.call_args_list
        ]
        self.assertEqual(
            opened_file_names,
            [
                "adc_configuration.txt",
                "dac39j84_0_1_2_configuration.txt",
                "dac39j84_0_1_2_configuration.txt",
                "control_lmk_configuration.txt",
                "JESD_configuration.txt",
            ],
        )
        send_data.assert_not_called()
        self.assertEqual(
            window.connection_log.toPlainText().count("已打开"),
            5,
        )

    def test_configuration_file_open_errors_are_reported_without_sending(self):
        window = self.make_window()
        missing_directory = Path(self.temp_dir.name) / "missing-config-files"
        adc_button = window.adda_widget.module_cards["ADC_readout"].config_file_buttons[
            "adc"
        ]

        with patch(
            "TDM_software.ADDA_CONFIG_DIRECTORY", missing_directory
        ), patch.object(QDesktopServices, "openUrl") as open_url, patch.object(
            QMessageBox, "warning"
        ) as warning, patch.object(window.tcp_manager, "send_data") as send_data:
            adc_button.click()

        open_url.assert_not_called()
        warning.assert_called_once()
        send_data.assert_not_called()
        self.assertIn("不存在", window.connection_log.toPlainText())

        with patch.object(
            QDesktopServices, "openUrl", return_value=False
        ) as open_url, patch.object(QMessageBox, "warning") as warning, patch.object(
            window.tcp_manager, "send_data"
        ) as send_data:
            adc_button.click()

        open_url.assert_called_once()
        warning.assert_called_once()
        send_data.assert_not_called()
        self.assertIn("系统无法打开", window.connection_log.toPlainText())


if __name__ == "__main__":
    unittest.main()
