# mainWindow.py
import sys
import os
import time
from queue import Queue

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import pyqtSlot, QThread, QTimer

from scifi_ui import Ui_MainWindow
from tcpClient import TCPClient
from fileWriter import FileWriter
from monitor import Monitor


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.raw_queue = Queue(maxsize=20000)

        self.net_thread = QThread()
        self.writer_thread = QThread()

        self.net = TCPClient(self.raw_queue)
        self.writer = FileWriter(
            self.raw_queue,
            filename=self._make_output_filename()
        )
        self.monitor = Monitor()

        self.net.moveToThread(self.net_thread)
        self.writer.moveToThread(self.writer_thread)

        self.net_thread.started.connect(self.net.start)
        self.writer_thread.started.connect(self.writer.start)

        self.ui.pb_setting.clicked.connect(self.apply_tcp_setting)
        self.ui.pb_start.clicked.connect(self.start_daq)
        self.ui.pb_stop.clicked.connect(self.stop_daq)

        self.ui.pb_stop.setEnabled(False)

        # ---------- TCPClient -> Monitor ----------
        self.net.connectedSignal.connect(self.monitor.onConnected)
        self.net.disconnectedSignal.connect(self.monitor.onDisconnected)
        self.net.errorSignal.connect(self.monitor.onError)
        self.net.commandSent.connect(self.monitor.onCommandSent)
        self.net.bytesReceived.connect(self.monitor.onBytesReceived)

        # ---------- FileWriter -> Monitor ----------
        self.writer.monitor.connect(self.monitor.onWriterMessage)
        self.writer.statsSignal.connect(self.monitor.onWriterStats)

        # ---------- Monitor -> UI ----------
        self.monitor.logMessage.connect(self.log)
        self.monitor.statsUpdated.connect(self.update_monitor)

        self.summary_timer = QTimer(self)
        self.summary_timer.setInterval(2000)
        self.summary_timer.timeout.connect(self.show_summary)

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(500)
        self.queue_timer.timeout.connect(self.update_queue_size)

        self.log("[UI] MainWindow initialized")

    def _make_output_filename(self):
        outdir = "data"
        os.makedirs(outdir, exist_ok=True)
        timestr = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(outdir, f"rawdaq_{timestr}.bin")

    def log(self, msg: str):
        self.ui.monitor_log.appendPlainText(msg)
        sb = self.ui.monitor_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def get_selected_mode(self) -> str:
        if self.ui.rb_normal.isChecked():
            return "normal"
        elif self.ui.rb_baseline.isChecked():
            return "baseline"
        elif self.ui.rb_calib.isChecked():
            return "calib"
        return "normal"

    @pyqtSlot()
    def apply_tcp_setting(self):
        ip = self.ui.line_ip.text().strip()
        port = self.ui.spin_port.value()
        mode = self.get_selected_mode()

        self.net.ip = ip
        self.net.port = port
        self.net.acqmode = mode

        self.log(f"[SETTING] TCP set to {ip}:{port}, mode={mode}")
        self.log("[SETTING] connecting and sending init commands...")

        self.net.connect_and_configure()

    @pyqtSlot()
    def start_daq(self):
        self.ui.pb_start.setEnabled(False)
        self.ui.pb_stop.setEnabled(True)

        self.writer.filename = self._make_output_filename()

        self.log("[DAQ] start requested")
        self.log(f"[DAQ] output file = {self.writer.filename}")

        if not self.writer_thread.isRunning():
            self.writer_thread.start()

        if not self.net.connected:
            self.log("[DAQ] TCP is not connected, apply setting first")
            self.ui.pb_start.setEnabled(True)
            self.ui.pb_stop.setEnabled(False)
            return

        if not self.net_thread.isRunning():
            self.net_thread.start()

        self.summary_timer.start()
        self.queue_timer.start()

    @pyqtSlot()
    def stop_daq(self):
        self.log("[DAQ] stop requested")

        self.summary_timer.stop()
        self.queue_timer.stop()

        self.net.stop()
        self.writer.stop()

        self.net_thread.quit()
        self.writer_thread.quit()

        self.net_thread.wait()
        self.writer_thread.wait()

        self.net.disconnect_tcp()

        self.log(self.monitor.snapshot_text())
        self.log("[DAQ] stopped")

        self.ui.pb_start.setEnabled(True)
        self.ui.pb_stop.setEnabled(False)

    @pyqtSlot()
    def update_queue_size(self):
        try:
            qsize = self.raw_queue.qsize()
        except Exception:
            qsize = -1
        self.monitor.onQueueSizeChanged(qsize)

    @pyqtSlot(dict)
    def update_monitor(self, stats: dict):
        pass

    @pyqtSlot()
    def show_summary(self):
        self.monitor._emit_stats()
        self.log(self.monitor.snapshot_text())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())