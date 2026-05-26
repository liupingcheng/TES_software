# monitor.py
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import time


class Monitor(QObject):

    statsUpdated = pyqtSignal(dict)
    logMessage = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.connected = False

        self.count_pkt_recv = 0
        self.count_bytes_recv = 0

        self.count_pkt_written = 0
        self.count_bytes_written = 0

        self.queue_size = 0

        self.t0 = time.time()
        self.last_write_ts = None

    def _emit_stats(self):

        now = time.time()
        dt = max(now - self.t0, 1e-9)

        stats = {
            "connected": self.connected,
            "packets_recv": self.count_pkt_recv,
            "bytes_recv": self.count_bytes_recv,
            "packets_written": self.count_pkt_written,
            "bytes_written": self.count_bytes_written,
            "rate_recv_pkt": self.count_pkt_recv / dt,
            "rate_recv_MB": self.count_bytes_recv / dt / 1024 / 1024,
            "rate_write_pkt": self.count_pkt_written / dt,
            "rate_write_MB": self.count_bytes_written / dt / 1024 / 1024,
            "queue_size": self.queue_size,
        }

        self.statsUpdated.emit(stats)

    # ---------------- TCP ----------------

    @pyqtSlot()
    def onConnected(self):

        self.connected = True
        self.logMessage.emit("[TCP] connected")
        self._emit_stats()

    @pyqtSlot()
    def onDisconnected(self):

        self.connected = False
        self.logMessage.emit("[TCP] disconnected")
        self._emit_stats()

    @pyqtSlot(str)
    def onError(self, msg):

        self.logMessage.emit(f"[ERROR] {msg}")

    @pyqtSlot(bytes)
    def onCommandSent(self, cmd):

        self.logMessage.emit(f"[CMD] sent: {cmd.hex()}")

    @pyqtSlot(int)
    def onBytesReceived(self, nbytes):

        self.count_pkt_recv += 1
        self.count_bytes_recv += nbytes

        # 降低日志频率
        if self.count_pkt_recv <= 5 or self.count_pkt_recv % 500 == 0:
            self.logMessage.emit(
                f"[TCP] recv packets={self.count_pkt_recv} bytes={self.count_bytes_recv}"
            )

    # ---------------- FileWriter ----------------

    @pyqtSlot(dict)
    def onWriterStats(self, stats):

        self.count_pkt_written = stats.get("written_packets", self.count_pkt_written)
        self.count_bytes_written = stats.get("written_bytes", self.count_bytes_written)
        self.last_write_ts = stats.get("last_write_ts", None)

    @pyqtSlot(int)
    def onQueueSizeChanged(self, qsize):

        self.queue_size = qsize

    @pyqtSlot(str)
    def onWriterMessage(self, msg):

        self.logMessage.emit(msg)

    def snapshot_text(self):

        now = time.time()
        dt = max(now - self.t0, 1e-9)

        return (
            f"[SUMMARY] connected={self.connected} | "
            f"recv_pkt={self.count_pkt_recv} | "
            f"recv_MB={self.count_bytes_recv/1024/1024:.2f} | "
            f"write_pkt={self.count_pkt_written} | "
            f"write_MB={self.count_bytes_written/1024/1024:.2f} | "
            f"recv_rate={self.count_pkt_recv/dt:.1f} pkt/s | "
            f"write_rate={self.count_pkt_written/dt:.1f} pkt/s | "
            f"queue={self.queue_size}"
        )