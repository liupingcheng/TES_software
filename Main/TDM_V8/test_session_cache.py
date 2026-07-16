import json
import os
import sys
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from TDM_software import MainWindow, SESSION_CACHE_KEY


class SessionCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(self.temp_dir.name, "tdm-session.ini")
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def make_settings(self):
        return QSettings(self.settings_path, QSettings.IniFormat)

    def make_window(self):
        window = MainWindow(self.make_settings())
        self.windows.append(window)
        return window

    def store_payload(self, payload):
        settings = self.make_settings()
        settings.setValue(
            SESSION_CACHE_KEY,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
        settings.sync()
        self.assertEqual(settings.status(), QSettings.NoError)

    def test_close_and_reopen_restores_all_settings_by_stable_ids(self):
        first = self.make_window()
        first.show()
        first.resize(1111, 777)
        self.app.processEvents()

        expected_connections = {}
        for index, board_type in enumerate(first.board_ip_edits):
            values = {
                "ip": f"10.20.{index}.1",
                "port": str(3000 + index),
                "local_ip": f"10.20.{index}.2",
            }
            expected_connections[board_type] = values
            first.board_ip_edits[board_type].setText(values["ip"])
            first.board_port_edits[board_type].setText(values["port"])
            first.board_local_ip_edits[board_type].setText(values["local_ip"])

        expected_bias_channels = {}
        expected_dac_pages = {}
        for board_index, board in enumerate(first.bias_boards):
            channel = board.chip_widgets[board_index].channel_widgets[board_index]
            values = {
                "type": (board_index + 1) % channel.combo_type.count(),
                "freq": 1234.0 + board_index,
                "amp": 0.2 + board_index * 0.1,
                "offset": 1.5 + board_index,
            }
            channel.set_config(values)
            expected_bias_channels[board.board_type] = (
                board_index,
                board_index,
                channel.get_config(),
            )
            dac_index = (board_index + 2) % len(board.chip_widgets)
            board.tabs.setCurrentWidget(board.chip_widgets[dac_index])
            expected_dac_pages[board.board_type] = dac_index

        first.bias_sub_tabs.setCurrentWidget(first.bias_boards[1])

        fpga_config = first.get_fpga_config()
        fpga_config["global"].update(
            {
                "mode": 1,
                "mode1_row": 7,
                "mode1_col": 5,
                "counter_limit": 4321,
                "dfb_enabled": True,
                "monitor_col": 9,
            }
        )
        fpga_config["cell_defaults"].update(
            {"kp": 16, "ki": 4, "adc_offset": 3, "dac_offset": 2}
        )
        fpga_config["cells"]["2_3"].update(
            {
                "enabled": True,
                "kp": 99,
                "ki": 88,
                "adc_offset": 7,
                "dac_offset": 6,
            }
        )
        success, message = first.set_fpga_config(fpga_config)
        self.assertTrue(success, message)
        expected_fpga = first.get_fpga_config()

        first.storage_path.setText("/tmp/tdm-data")
        first.storage_format.setCurrentIndex(1)
        first.file_prefix.setText("experiment_42")
        first.save_interval.setValue(321)

        storage_index = first.tabs.indexOf(first.main_pages["storage"])
        first.tabs.tabBar().moveTab(storage_index, 0)
        first.tabs.setCurrentWidget(first.main_pages["storage"])

        self.assertTrue(first.close())
        self.app.processEvents()

        second = self.make_window()

        for board_type, values in expected_connections.items():
            self.assertEqual(second.board_ip_edits[board_type].text(), values["ip"])
            self.assertEqual(second.board_port_edits[board_type].text(), values["port"])
            self.assertEqual(
                second.board_local_ip_edits[board_type].text(), values["local_ip"]
            )

        for board in second.bias_boards:
            chip_index, channel_index, values = expected_bias_channels[board.board_type]
            channel = board.chip_widgets[chip_index].channel_widgets[channel_index]
            self.assertEqual(channel.get_config(), values)
            self.assertEqual(
                board.tabs.currentWidget().chip_id,
                expected_dac_pages[board.board_type],
            )
            self.assertEqual(board.txt_ip.text(), expected_connections[board.board_type]["ip"])
            self.assertEqual(
                board.txt_port.text(), expected_connections[board.board_type]["port"]
            )

        self.assertEqual(second.bias_sub_tabs.currentWidget().board_type, "Bias2")
        self.assertEqual(second._current_main_page_id(), "storage")
        self.assertEqual(second.get_fpga_config(), expected_fpga)
        self.assertEqual(second.storage_path.text(), "/tmp/tdm-data")
        self.assertEqual(second.storage_format.currentIndex(), 1)
        self.assertEqual(second.file_prefix.text(), "experiment_42")
        self.assertEqual(second.save_interval.value(), 321)
        self.assertEqual(second.size(), first.size())

        self.assertEqual(second.tcp_manager.clients, {})
        for board_type, button in second.board_connection_btns.items():
            self.assertEqual(button.text(), "Connect", board_type)

    def test_missing_fields_keep_defaults_and_extra_fields_are_ignored(self):
        source = self.make_window()
        payload = source.collect_session_cache()
        payload["storage"]["path"] = "/tmp/from-old-cache"
        del payload["storage"]["prefix"]
        payload["storage"]["removed_future_field"] = "ignored"
        del payload["bias"]["boards"]["Bias1"]["dacs"]["dac_0"]["ch_0"]["freq"]
        payload["bias"]["boards"]["Bias1"]["dacs"]["dac_0"]["ch_0"][
            "removed_field"
        ] = "ignored"
        del payload["fpga"]["global"]["counter_limit"]
        payload["fpga"]["global"]["monitor_col"] = 6
        payload["fpga"]["global"]["removed_register"] = 123
        payload["connections"]["boards"]["removed_board"] = {
            "ip": "203.0.113.1",
            "port": "24",
            "local_ip": "203.0.113.2",
        }
        self.store_payload(payload)

        restored = self.make_window()
        self.assertEqual(restored.storage_path.text(), "/tmp/from-old-cache")
        self.assertEqual(restored.file_prefix.text(), "TDM_data")
        self.assertNotIn("removed_board", restored.board_ip_edits)
        restored_channel = restored.bias_boards[0].chip_widgets[0].channel_widgets[0]
        self.assertEqual(restored_channel.spin_freq.value(), 1000.0)
        self.assertEqual(restored.fpga_widget.counter_limit.value(), 2500)
        self.assertEqual(restored.fpga_widget.monitor_col.value(), 6)

    def test_only_confirmed_editor_values_are_cached(self):
        first = self.make_window()
        first.show()
        QApplication.setActiveWindow(first)
        QTest.mouseClick(first.file_prefix, Qt.LeftButton)
        self.app.processEvents()
        self.assertTrue(first.file_prefix.hasFocus())
        first.file_prefix.setText("not-confirmed")
        self.assertTrue(first.close())
        self.app.processEvents()

        second = self.make_window()
        self.assertEqual(second.file_prefix.text(), "TDM_data")
        second.show()
        QApplication.setActiveWindow(second)
        QTest.mouseClick(second.file_prefix, Qt.LeftButton)
        self.app.processEvents()
        second.file_prefix.setText("confirmed-prefix")
        QTest.keyClick(second.file_prefix, Qt.Key_Return)
        self.assertTrue(second.close())
        self.app.processEvents()

        third = self.make_window()
        self.assertEqual(third.file_prefix.text(), "confirmed-prefix")

    def test_invalid_fpga_section_does_not_block_other_sections(self):
        source = self.make_window()
        payload = source.collect_session_cache()
        payload["connections"]["boards"]["Bias1"]["ip"] = "10.99.0.1"
        payload["storage"]["path"] = "/tmp/partial-restore"
        payload["fpga"] = {"type": "fpga", "schema_version": 999}
        self.store_payload(payload)

        restored = self.make_window()
        self.assertEqual(restored.board_ip_edits["Bias1"].text(), "10.99.0.1")
        self.assertEqual(restored.storage_path.text(), "/tmp/partial-restore")
        self.assertEqual(restored.fpga_widget.counter_limit.value(), 2500)
        self.assertIn("fpga 恢复失败", restored.connection_log.toPlainText())

    def test_corrupt_or_newer_root_cache_falls_back_to_defaults(self):
        settings = self.make_settings()
        settings.setValue(SESSION_CACHE_KEY, "{not-json")
        settings.sync()

        corrupt = self.make_window()
        self.assertEqual(corrupt.file_prefix.text(), "TDM_data")
        self.assertIn("自动缓存读取失败", corrupt.connection_log.toPlainText())

        self.store_payload({"schema_version": 999, "storage": {"path": "/bad"}})
        newer = self.make_window()
        self.assertEqual(newer.storage_path.text(), "")
        self.assertIn("高于当前支持", newer.connection_log.toPlainText())


if __name__ == "__main__":
    unittest.main()
