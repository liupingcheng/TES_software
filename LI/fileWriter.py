# fileWriter.py

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
import queue
import os
import time


class FileWriter(QObject):

    monitor = pyqtSignal(str)
    statsSignal = pyqtSignal(dict)

    def __init__(
        self,
        raw_queue,
        filename="raw_stream.bin",
        flush_every=500,
        buffer_size=1024 * 1024  # 1 MB
    ):

        super().__init__()

        self.raw_queue = raw_queue
        self.filename = filename

        self.flush_every = flush_every
        self.buffer_size = buffer_size

        self.file = None
        self.running = False

        self.write_buffer = bytearray()

        self.packet_count = 0
        self.total_bytes_written = 0

        self.t0 = None
        self.last_write_ts = None

    def _log(self, msg):
        self.monitor.emit(msg)

    def _emit_stats(self):

        now = time.time()
        dt = max(now - self.t0, 1e-9)

        stats = {
            "written_packets": self.packet_count,
            "written_bytes": self.total_bytes_written,
            "write_rate_pkt": self.packet_count / dt,
            "write_rate_MB": self.total_bytes_written / dt / 1024 / 1024,
            "last_write_ts": self.last_write_ts,
        }

        self.statsSignal.emit(stats)

    @pyqtSlot()
    def start(self):

        if self.running:
            return

        self.running = True

        self.packet_count = 0
        self.total_bytes_written = 0
        self.t0 = time.time()

        self.write_buffer = bytearray()

        outdir = os.path.dirname(self.filename)
        if outdir:
            os.makedirs(outdir, exist_ok=True)

        self.file = open(self.filename, "wb")

        self._log(f"[FileWriter] started → {self.filename}")

        while self.running:

            try:
                packet = self.raw_queue.get(timeout=0.2)

            except queue.Empty:
                continue

            if packet is None:
                break

            self.write_packet(packet)

        # 结束时写出剩余buffer
        self.flush_buffer()

        self._close_file()

        self._log("[FileWriter] stopped")

    def write_packet(self, packet):

        payload = getattr(packet, "payload", None)

        if payload is None or len(payload) == 0:
            return

        ts = getattr(packet, "ts", time.time())

        # 写入 RAM buffer
        self.write_buffer.extend(payload)

        self.packet_count += 1
        self.total_bytes_written += len(payload)
        self.last_write_ts = ts

        # ---------- buffer满 ----------
        if len(self.write_buffer) >= self.buffer_size:
            self.flush_buffer()

        # ---------- 定期flush ----------
        elif self.packet_count % self.flush_every == 0:
            self.flush_buffer()

        # ---------- 降低日志频率 ----------
        if self.packet_count <= 5 or self.packet_count % 2000 == 0:

            self._log(
                f"[FileWriter] packet={self.packet_count} "
                f"MB={self.total_bytes_written/1024/1024:.2f}"
            )

        # ---------- 更新统计 ----------
        if self.packet_count <= 5 or self.packet_count % 100 == 0:
            self._emit_stats()

    def flush_buffer(self):

        if not self.write_buffer:
            return

        self.file.write(self.write_buffer)
        self.file.flush()

        self.write_buffer.clear()

    def _close_file(self):

        if self.file is not None:

            try:
                self.file.flush()
                self.file.close()

            except Exception:
                pass

            self.file = None

    @pyqtSlot()
    def stop(self):

        self.running = False

        try:
            self.raw_queue.put_nowait(None)

        except queue.Full:
            pass

        self._log("[FileWriter] stop requested")