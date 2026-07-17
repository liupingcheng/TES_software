import os
import sys
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
V8_DIRECTORY = Path(__file__).resolve().parents[1] / "TDM_V8"
sys.path.insert(0, str(V8_DIRECTORY))

from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from adda_config_sender import ADDAConfigSender, ConfigFileError, parse_configuration_file


class ADDAConfigSenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.send_calls = []
        self.send_result = True
        self.senders = []

    def tearDown(self):
        for sender in self.senders:
            sender.cancel_all("test cleanup")
            sender.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def write_config(self, name, contents):
        path = Path(self.temp_dir.name) / name
        path.write_text(contents, encoding="utf-8")
        return path

    def make_sender(self, command_delay=1, wait_delay=5, reply_timeout=100):
        def send(board_type, data):
            self.send_calls.append((board_type, data))
            return self.send_result

        sender = ADDAConfigSender(
            send,
            command_delay_ms=command_delay,
            wait_marker_delay_ms=wait_delay,
            reply_timeout_ms=reply_timeout,
        )
        self.senders.append(sender)
        return sender

    def test_parse_32_bit_wait_marker_and_64_bit_jesd(self):
        standard_path = self.write_config(
            "standard.txt",
            "\n01020304\nFFFFFFFF\nAABBCCDD\n",
        )
        steps, count = parse_configuration_file(standard_path, 4)
        self.assertEqual(count, 2)
        self.assertEqual(steps[0].payload, b"\x01\x02\x03\x04")
        self.assertTrue(steps[1].is_wait)
        self.assertEqual(steps[2].payload, b"\xAA\xBB\xCC\xDD")

        jesd_path = self.write_config("jesd.txt", "1000000800000001\n")
        steps, count = parse_configuration_file(jesd_path, 8)
        self.assertEqual(count, 1)
        self.assertEqual(steps[0].payload, b"\x10\x00\x00\x08\x00\x00\x00\x01")

    def test_parse_rejects_empty_invalid_hex_and_wrong_width(self):
        cases = (
            ("empty.txt", "\n\n", "为空"),
            ("only-wait.txt", "FFFFFFFF\n", "为空"),
            ("invalid.txt", "01020X04\n", "非十六进制"),
            ("short.txt", "1234\n", "长度错误"),
            ("comment.txt", "01020304 # comment\n", "长度错误"),
        )
        for name, contents, expected_message in cases:
            with self.subTest(name=name):
                path = self.write_config(name, contents)
                with self.assertRaisesRegex(ConfigFileError, expected_message):
                    parse_configuration_file(path, 4)

    def test_sequence_waits_for_split_reply_and_preserves_extra_data(self):
        path = self.write_config(
            "sequence.txt",
            "01020304\nFFFFFFFF\nAABBCCDD\n",
        )
        sender = self.make_sender()
        progress = QSignalSpy(sender.progress)
        finished = QSignalSpy(sender.finished)

        self.assertEqual(sender.start("ADC_readout", "adc_registers", path, 4), (True, ""))
        QTest.qWait(15)
        self.assertEqual(self.send_calls, [("ADC_readout", b"\x01\x02\x03\x04")])

        self.assertEqual(sender.feed_received("ADC_readout", b"\x10\x20"), b"")
        QTest.qWait(10)
        self.assertEqual(len(progress), 0)
        self.assertEqual(len(self.send_calls), 1)

        self.assertEqual(sender.feed_received("ADC_readout", b"\x30\x40"), b"")
        QTest.qWait(60)
        self.assertEqual(list(progress[0]), ["ADC_readout", "adc_registers", 1, 2])
        self.assertEqual(self.send_calls[-1], ("ADC_readout", b"\xAA\xBB\xCC\xDD"))

        self.assertEqual(
            sender.feed_received("ADC_readout", b"ACK!extra"),
            b"extra",
        )
        QTest.qWait(5)
        self.assertEqual(list(progress[1]), ["ADC_readout", "adc_registers", 2, 2])
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0][2])
        self.assertFalse(sender.is_active("ADC_readout"))

    def test_timeout_send_failure_cancel_and_per_board_exclusion(self):
        path = self.write_config("single.txt", "01020304\n")

        timeout_sender = self.make_sender(reply_timeout=20)
        timeout_finished = QSignalSpy(timeout_sender.finished)
        self.assertTrue(timeout_sender.start("ADC_readout", "adc_registers", path, 4)[0])
        self.assertFalse(timeout_sender.start("ADC_readout", "adc_registers", path, 4)[0])
        self.assertTrue(timeout_sender.start("FB_DAC", "dac_registers", path, 4)[0])
        QTest.qWait(50)
        self.assertEqual(len(timeout_finished), 2)
        self.assertTrue(all(not call[2] for call in timeout_finished))
        self.assertTrue(all("超时" in call[3] for call in timeout_finished))

        self.send_result = False
        failed_sender = self.make_sender()
        failed_finished = QSignalSpy(failed_sender.finished)
        self.assertTrue(failed_sender.start("gate_DAC", "dac_registers", path, 4)[0])
        QTest.qWait(15)
        self.assertEqual(len(failed_finished), 1)
        self.assertIn("发送失败", failed_finished[0][3])

        self.send_result = True
        cancelled_sender = self.make_sender(command_delay=50)
        cancelled_finished = QSignalSpy(cancelled_sender.finished)
        self.assertTrue(cancelled_sender.start("fpga", "clock_output", path, 4)[0])
        self.assertTrue(cancelled_sender.cancel("fpga", "连接断开"))
        self.assertEqual(len(cancelled_finished), 1)
        self.assertIn("连接断开", cancelled_finished[0][3])
        QTest.qWait(60)
        self.assertFalse(cancelled_sender.is_active("fpga"))


if __name__ == "__main__":
    unittest.main()
