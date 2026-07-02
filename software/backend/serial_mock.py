import json
import random
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class MockSerialWorker(QObject):
    data_received = pyqtSignal(str, float, float)
    raw_data_received = pyqtSignal(int, list, list)
    data_raw_received = pyqtSignal(int, list, list, int)  # led, ch0, ch1, presamples
    monitor_received = pyqtSignal(list, list)
    status_changed = pyqtSignal(str)
    config_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.generate)

        self.config = {
            "osr": 5,
            "presamples": 80,
            "samples": 160,
            "pulse_ms": 170,
            "channels": 7,
            "deadtime": 3,
            "brightness_r": 1000,
            "brightness_b": 1000,
            "brightness_g": 1000,
        }
        self.r = 0.45
        self.g = 0.55
        self.b = 0.35
        self.ma_r = 15.0
        self.ma_g = 14.2
        self.ma_b = 16.5
        self.measuring = False
        self.mode = "continuous"
        self._monitor_enabled = False
        self._active_leds = [0, 1, 2]

    def start(self):
        self.timer.start(50)
        self.connection_changed.emit(True)

    def stop(self):
        self.timer.stop()
        self.measuring = False
        self.connection_changed.emit(False)

    def send(self, msg):
        try:
            cmd = json.loads(msg.strip())
        except json.JSONDecodeError:
            return

        c = cmd.get("cmd")
        if c == "start":
            self.mode = cmd.get("mode", "continuous")
            self.measuring = True
            status = "measuring"
            if "send_raw" in cmd:
                self.config["send_raw"] = cmd["send_raw"]
            if "channels" in cmd:
                self.config["channels"] = cmd["channels"]
                self._update_active_leds()
            if self.mode == "single":
                self._single_shot()
            self.status_changed.emit(status)
        elif c == "stop":
            self.measuring = False
            self.status_changed.emit("monitoring" if self._monitor_enabled else "idle")
        elif c == "set":
            for k in (
                "osr",
                "presamples",
                "samples",
                "pulse_ms",
                "channels",
                "deadtime",
                "brightness_r",
                "brightness_b",
                "brightness_g",
                "send_raw",
            ):
                if k in cmd:
                    self.config[k] = cmd[k]
            if "channels" in cmd:
                self._update_active_leds()
            self.config_received.emit(dict(self.config))
        elif c == "config":
            self.config_received.emit(dict(self.config))
        elif c == "monitor":
            self._monitor_enabled = bool(cmd.get("enable", False))
            if not self.measuring:
                self.status_changed.emit(
                    "monitoring" if self._monitor_enabled else "idle"
                )

    def send_json(self, obj):
        self.send(json.dumps(obj) + "\n")

    def send_start(self, mode="continuous", send_raw=None, **kwargs):
        cmd = {"cmd": "start", "mode": mode}
        if send_raw is not None:
            cmd["send_raw"] = 1 if send_raw else 0
        cmd.update(kwargs)
        self.send(json.dumps(cmd) + "\n")

    def send_stop(self):
        self.send_json({"cmd": "stop"})

    def send_set(self, send_raw=None, **kwargs):
        cmd = {"cmd": "set"}
        if send_raw is not None:
            cmd["send_raw"] = 1 if send_raw else 0
        cmd.update(kwargs)
        self.send(json.dumps(cmd) + "\n")

    def send_get_config(self):
        self.send_json({"cmd": "config"})

    def send_monitor(self, enable=True):
        self.send_json({"cmd": "monitor", "enable": 1 if enable else 0})

    def _update_active_leds(self):
        ch = self.config.get("channels", 7)
        self._active_leds = [i for i in range(3) if ch & (1 << i)]

    def generate(self):
        if not self.measuring and not self._monitor_enabled:
            return

        if not self.measuring and self._monitor_enabled:
            ch0 = [random.randint(100_000, 8_000_000) for _ in range(20)]
            ch1 = [random.randint(100_000, 8_000_000) for _ in range(20)]
            self.monitor_received.emit(ch0, ch1)
            return

        if self.mode == "single":
            return

        self.r = max(0.0, min(2.0, self.r + random.uniform(-0.01, 0.01)))
        self.g = max(0.0, min(2.0, self.g + random.uniform(-0.01, 0.01)))
        self.b = max(0.0, min(2.0, self.b + random.uniform(-0.01, 0.01)))

        cur_r = max(0.0, min(30.0, self.ma_r + random.uniform(-0.1, 0.1)))
        cur_g = max(0.0, min(30.0, self.ma_g + random.uniform(-0.1, 0.1)))
        cur_b = max(0.0, min(30.0, self.ma_b + random.uniform(-0.1, 0.1)))

        self.data_received.emit("R", self.r, cur_r)
        self.data_received.emit("B", self.b, cur_b)
        self.data_received.emit("G", self.g, cur_g)

        if self.config.get("send_raw", 0):
            presamples = self.config.get("presamples", 80)
            samples = self.config.get("samples", 160)
            total = presamples + samples
            for led in self._active_leds:
                ch0 = [random.randint(100_000, 8_000_000) for _ in range(total)]
                ch1 = [random.randint(100_000, 8_000_000) for _ in range(total)]
                self.data_raw_received.emit(led, ch0, ch1, presamples)
                if self._monitor_enabled:
                    self.monitor_received.emit(ch0, ch1)

    def _single_shot(self):
        self.data_received.emit("R", self.r, self.ma_r)
        self.data_received.emit("B", self.b, self.ma_b)
        self.data_received.emit("G", self.g, self.ma_g)

        presamples = self.config.get("presamples", 80)
        samples = self.config.get("samples", 160)
        total = presamples + samples
        for led in self._active_leds:
            dark_ch0 = [random.randint(100_000, 8_000_000) for _ in range(presamples)]
            dark_ch1 = [random.randint(100_000, 8_000_000) for _ in range(presamples)]
            light_ch0 = [random.randint(100_000, 8_000_000) for _ in range(samples)]
            light_ch1 = [random.randint(100_000, 8_000_000) for _ in range(samples)]
            all_ch0 = dark_ch0 + light_ch0
            all_ch1 = dark_ch1 + light_ch1
            self.data_raw_received.emit(led, all_ch0, all_ch1, presamples)
            if self._monitor_enabled:
                self.monitor_received.emit(all_ch0, all_ch1)

        self.measuring = False
        self.status_changed.emit("monitoring" if self._monitor_enabled else "idle")
