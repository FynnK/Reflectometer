import json
import serial
import threading
from PyQt6.QtCore import QObject, pyqtSignal


class SerialWorker(QObject):
    data_received = pyqtSignal(str, float, float)
    raw_data_received = pyqtSignal(int, list, list)
    data_raw_received = pyqtSignal(int, list, list, int)  # led, ch0, ch1, presamples
    monitor_received = pyqtSignal(list, list)
    status_changed = pyqtSignal(str)
    config_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(self, port, baud=460800):
        super().__init__()
        self.port = port
        self.baud = baud
        self.running = False

    def start(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            self.running = True
            self.connection_changed.emit(True)
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connection_changed.emit(False)

    def stop(self):
        self.running = False
        if hasattr(self, "ser"):
            try:
                self.ser.close()
            except Exception:
                pass
        self.connection_changed.emit(False)

    def send(self, msg):
        if hasattr(self, "ser") and self.ser and self.ser.is_open:
            try:
                self.ser.write(msg.encode())
                self.ser.flush()
            except Exception as e:
                print(f"Send error: {e}")

    def send_json(self, obj):
        self.send(json.dumps(obj) + "\n")

    def send_start(self, mode="continuous", send_raw=None, **kwargs):
        cmd = {"cmd": "start", "mode": mode}
        if send_raw is not None:
            cmd["send_raw"] = 1 if send_raw else 0
        cmd.update(kwargs)
        self.send_json(cmd)

    def send_stop(self):
        self.send_json({"cmd": "stop"})

    def send_set(self, send_raw=None, **kwargs):
        cmd = {"cmd": "set"}
        if send_raw is not None:
            cmd["send_raw"] = 1 if send_raw else 0
        cmd.update(kwargs)
        self.send_json(cmd)

    def send_get_config(self):
        self.send_json({"cmd": "config"})

    def send_monitor(self, enable=True):
        self.send_json({"cmd": "monitor", "enable": 1 if enable else 0})

    def loop(self):
        while self.running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                self._process(line)
            except Exception:
                pass

    def _process(self, line):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        ev = msg.get("ev")
        if ev == "data":
            # r=GPIO3(Red), b=GPIO4(Blue), g=GPIO5(Green)
            r = msg.get("r", [0, 0])
            b = msg.get("b", [0, 0])
            g = msg.get("g", [0, 0])
            self.data_received.emit("R", r[0], r[1])
            self.data_received.emit("B", b[0], b[1])
            self.data_received.emit("G", g[0], g[1])
        elif ev == "raw":
            led = msg.get("led", 0)
            ch0 = msg.get("ch0", [])
            ch1 = msg.get("ch1", [])
            presamples = msg.get("presamples", 0)
            if presamples > 0:
                self.data_raw_received.emit(led, ch0, ch1, presamples)
            else:
                self.raw_data_received.emit(led, ch0, ch1)
        elif ev == "data_raw":
            led = msg.get("led", 0)
            ch0 = msg.get("ch0", [])
            ch1 = msg.get("ch1", [])
            presamples = msg.get("presamples", 0)
            self.data_raw_received.emit(led, ch0, ch1, presamples)
        elif ev == "monitor":
            ch0 = msg.get("ch0", [])
            ch1 = msg.get("ch1", [])
            self.monitor_received.emit(ch0, ch1)
        elif ev == "status":
            self.status_changed.emit(msg.get("state", ""))
        elif ev == "config":
            self.config_received.emit(msg)
        elif ev == "error":
            print(f"Firmware error: {msg.get('msg', '')}")
