# gui.py

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QComboBox,
    QSlider,
    QSpinBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer
import pyqtgraph as pg
import json
import time
from collections import deque
import serial.tools.list_ports

from backend.serial_mock import MockSerialWorker
from backend.serial_worker import SerialWorker

ADC_FULL_SCALE = 8388608.0
ADC_VREF = 1.2
R_SENSE = 10.0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Optical System")
        self.resize(1200, 850)

        self.worker = None
        self.mode = "esp32"  # overridden by mode_box signal below

        self.max_points = 150

        self.r = deque(maxlen=self.max_points)
        self.g = deque(maxlen=self.max_points)
        self.b = deque(maxlen=self.max_points)

        self.base_r = None
        self.base_g = None
        self.base_b = None
        self.baseline_ready = False

        self.raw_data = {}  # led -> {"ch0": [...], "ch1": [...]}
        self.monitor_buf = deque(
            maxlen=240
        )  # resized by send_config() before each measurement
        self.connected = False
        self.device_state = "idle"
        self.last_data_time = 0
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._check_heartbeat)
        self.alpha = 0.4
        self.filtered_score = 0.0
        self.stable_class = "WAITING"
        self.state_window = deque(maxlen=7)
        self._single_shot_pending = False
        self._single_shot_remaining = 0
        self._monitor_led = 0
        self._monitor_cycle = {
            0: ([], []),
            1: ([], []),
            2: ([], []),
        }  # led -> (ch0[], ch1[])
        self._monitor_cycle_seen = set()

        # UI LAYOUT
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout()
        root.setLayout(layout)

        # TOP BAR
        top = QHBoxLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItems(["mock", "esp32"])

        self.port_box = QComboBox()
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setToolTip("Refresh ports")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.btn_connect.setEnabled(False)
        self.heartbeat = QLabel("●")
        self.heartbeat.setStyleSheet("font-size: 20px; color: red;")
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.toggle_measurement)
        self.btn_start.setEnabled(False)
        self.mon_cb = QCheckBox("Monitor")
        self.mon_cb.toggled.connect(self.toggle_monitor)
        self.btn_calibrate = QPushButton("Calibrate")
        self.btn_calibrate.clicked.connect(self.capture_baseline)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_plots)
        self.status = QLabel("Disconnected")

        self.mode_box.currentTextChanged.connect(self.set_mode)
        self.mode_box.setCurrentIndex(1)  # default to esp32
        self.refresh_ports()

        top.addWidget(QLabel("Mode:"))
        top.addWidget(self.mode_box)
        top.addWidget(QLabel("Port:"))
        top.addWidget(self.port_box)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_connect)
        top.addWidget(self.heartbeat)
        top.addWidget(self.btn_start)
        top.addWidget(self.mon_cb)
        top.addWidget(self.btn_calibrate)
        top.addWidget(self.btn_clear)
        top.addWidget(self.status)
        layout.addLayout(top)

        # LED INTENSITY
        led_group = QGroupBox("LEDs")
        led_grid = QGridLayout()

        self.chk_r = QCheckBox("Red")
        self.chk_r.setChecked(True)
        self.brightness_r = QSpinBox()
        self.brightness_r.setRange(0, 2000)
        self.brightness_r.setValue(1000)
        led_grid.addWidget(self.chk_r, 0, 0)
        led_grid.addWidget(self.brightness_r, 0, 1)

        self.chk_g = QCheckBox("Green")
        self.chk_g.setChecked(True)
        self.brightness_g = QSpinBox()
        self.brightness_g.setRange(0, 2000)
        self.brightness_g.setValue(1000)
        led_grid.addWidget(self.chk_g, 0, 2)
        led_grid.addWidget(self.brightness_g, 0, 3)

        self.chk_b = QCheckBox("Blue")
        self.chk_b.setChecked(True)
        self.brightness_b = QSpinBox()
        self.brightness_b.setRange(0, 2000)
        self.brightness_b.setValue(1000)
        led_grid.addWidget(self.chk_b, 0, 4)
        led_grid.addWidget(self.brightness_b, 0, 5)

        led_group.setLayout(led_grid)
        layout.addWidget(led_group)

        # CONFIG PANEL
        config_group = QGroupBox("Measurement Config")
        config_grid = QGridLayout()

        config_grid.addWidget(QLabel("OSR:"), 0, 0)
        self.osr_box = QComboBox()
        osr_labels = ["128", "256", "512", "1024", "2048", "4096", "8192", "16384"]
        osr_values = [0, 1, 2, 3, 4, 5, 6, 7]
        for lbl, val in zip(osr_labels, osr_values):
            self.osr_box.addItem(lbl, val)
        self.osr_box.setCurrentIndex(5)
        config_grid.addWidget(self.osr_box, 0, 1)

        config_grid.addWidget(QLabel("Presamples:"), 0, 2)
        self.presamples_spin = QSpinBox()
        self.presamples_spin.setRange(1, 100000)
        self.presamples_spin.setValue(80)
        config_grid.addWidget(self.presamples_spin, 0, 3)

        self.lbl_actual_presamples = QLabel("")
        self.lbl_actual_presamples.setStyleSheet("color: #888;")
        config_grid.addWidget(self.lbl_actual_presamples, 0, 4)

        config_grid.addWidget(QLabel("Samples:"), 0, 5)
        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(1, 100000)
        self.samples_spin.setValue(160)
        config_grid.addWidget(self.samples_spin, 0, 6)

        self.lbl_actual_samples = QLabel("")
        self.lbl_actual_samples.setStyleSheet("color: #888;")
        config_grid.addWidget(self.lbl_actual_samples, 0, 7)

        config_grid.addWidget(QLabel("Deadtime:"), 0, 8)
        self.deadtime_spin = QSpinBox()
        self.deadtime_spin.setRange(0, 1000)
        self.deadtime_spin.setValue(3)
        config_grid.addWidget(self.deadtime_spin, 0, 9)

        config_grid.addWidget(QLabel("Est. time / LED:"), 0, 10)
        self.lbl_est_time = QLabel("")
        self.lbl_est_time.setStyleSheet("color: #888;")
        config_grid.addWidget(self.lbl_est_time, 0, 11)

        self.send_raw_cb = QCheckBox("Send Raw")
        self.send_raw_cb.setChecked(True)
        self.send_raw_cb.setToolTip(
            "Stream raw ADC samples for software post-processing"
        )
        config_grid.addWidget(self.send_raw_cb, 0, 12)

        self.btn_apply_config = QPushButton("Apply Config")
        self.btn_apply_config.clicked.connect(self.send_config)
        config_grid.addWidget(self.btn_apply_config, 0, 13)

        self.btn_single = QPushButton("Single Shot")
        self.btn_single.clicked.connect(self.send_single)
        config_grid.addWidget(self.btn_single, 0, 14)

        config_group.setLayout(config_grid)
        layout.addWidget(config_group)

        self.osr_box.currentIndexChanged.connect(self._update_est_time)
        self.presamples_spin.valueChanged.connect(self._update_est_time)
        self.samples_spin.valueChanged.connect(self._update_est_time)
        self.deadtime_spin.valueChanged.connect(self._update_est_time)
        self.chk_r.toggled.connect(self._update_est_time)
        self.chk_g.toggled.connect(self._update_est_time)
        self.chk_b.toggled.connect(self._update_est_time)

        self._update_est_time()

        # DASHBOARD
        dash = QHBoxLayout()
        self.big_score = QLabel("---")
        self.big_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big_score.setStyleSheet("font-size: 48px; font-weight: bold;")

        self.class_label = QLabel("WAITING")
        self.class_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.class_label.setStyleSheet("font-size: 24px;")

        self.traffic = QLabel("●")
        self.traffic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.traffic.setStyleSheet("font-size: 80px; color: gray;")

        dash.addWidget(self.big_score)
        dash.addWidget(self.class_label)
        dash.addWidget(self.traffic)
        layout.addLayout(dash)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)

        self.plot.setYRange(0.0, 1.5)
        self.plot.setLabel("left", "Reflexion (Verhältniswert)", colors="#FFFFFF")
        self.plot.setLabel("bottom", "Messpunkte")

        self.curve_r = self.plot.plot(pen=pg.mkPen("r", width=1.5))
        self.curve_g = self.plot.plot(pen=pg.mkPen("g", width=1.5))
        self.curve_b = self.plot.plot(pen=pg.mkPen("b", width=1.5))

        # BASELINE-LINIEN (Linke Achse, dünn & teiltransparent gestrichelt)
        pen_base_r = pg.mkPen((255, 0, 0, 100), width=1.0, style=Qt.PenStyle.DashLine)
        pen_base_g = pg.mkPen((0, 255, 0, 100), width=1.0, style=Qt.PenStyle.DashLine)
        pen_base_b = pg.mkPen((0, 0, 255, 100), width=1.0, style=Qt.PenStyle.DashLine)

        self.line_base_r = pg.InfiniteLine(angle=0, pen=pen_base_r)
        self.line_base_g = pg.InfiniteLine(angle=0, pen=pen_base_g)
        self.line_base_b = pg.InfiniteLine(angle=0, pen=pen_base_b)

        self.line_base_r.hide()
        self.line_base_g.hide()
        self.line_base_b.hide()

        self.plot.addItem(self.line_base_r)
        self.plot.addItem(self.line_base_g)
        self.plot.addItem(self.line_base_b)

        layout.addWidget(self.plot)

        # MONITOR PLOT (rolling oscilloscope)
        self.monitor_plot = pg.PlotWidget()
        self.monitor_plot.showGrid(x=True, y=True)
        self.monitor_plot.setLabel("left", "Current (mA)")
        self.monitor_plot.setLabel("bottom", "Sample")
        self.monitor_plot.setYRange(0.0, 30.0)
        self.monitor_plot.hide()
        self.monitor_label = QLabel("")
        self.monitor_label.hide()
        self._cycle_curves = {}
        for led, color in [(0, (255, 0, 0)), (1, (0, 0, 255)), (2, (0, 200, 0))]:
            self._cycle_curves[led] = (
                self.monitor_plot.plot(pen=pg.mkPen(color, width=1.5)),
                self.monitor_plot.plot(pen=pg.mkPen((180, 180, 180), width=1.5)),
            )
        layout.addWidget(self.monitor_label)
        layout.addWidget(self.monitor_plot)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(50)

        self.heartbeat_timer.start(2000)

    def set_mode(self, mode):
        if self.worker:
            self._disconnect()
        self.mode = mode
        if mode == "esp32":
            self.port_box.show()
            self.btn_refresh.show()
            self.btn_connect.show()
            self.heartbeat.show()
            self.port_box.setEnabled(True)
            self.btn_start.setEnabled(False)
            self.btn_connect.setEnabled(True)
            if self.port_box.count() == 0:
                self.refresh_ports()
        else:
            self.port_box.hide()
            self.btn_refresh.hide()
            self.btn_connect.hide()
            self.heartbeat.hide()
            self.btn_connect.setText("Connect")
            self.on_connection_changed(True)
            self.btn_start.setEnabled(True)

    def toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if self.worker:
            return
        port = self.port_box.currentText()
        self.worker = SerialWorker(port)
        self.worker.data_received.connect(self.on_data)
        self.worker.raw_data_received.connect(self.on_raw_data)
        self.worker.data_raw_received.connect(self.on_data_raw)
        self.worker.status_changed.connect(self.on_status)
        self.worker.config_received.connect(self.on_config)
        self.worker.monitor_received.connect(self.on_monitor_data)
        self.worker.connection_changed.connect(self.on_connection_changed)
        self.worker.start()
        if not self.worker:
            return
        self.worker.send_get_config()

    def _led_channels(self):
        mask = 0
        if self.chk_r.isChecked():
            mask |= 1
        if self.chk_g.isChecked():
            mask |= 4  # bit2 = green (GPIO5)
        if self.chk_b.isChecked():
            mask |= 2  # bit1 = blue (GPIO4)
        return mask

    def _disconnect(self):
        if not self.worker:
            return
        if self.mode == "esp32":
            self.worker.send_stop()
        self.worker.stop()
        # self.worker cleaned up by on_connection_changed(False)
        self.line_base_r.hide()
        self.line_base_g.hide()
        self.line_base_b.hide()
        self.baseline_ready = False

    def toggle_measurement(self):
        if not self.worker:
            if self.mode == "mock":
                self._start_mock()
                return
            return

        if self.mode == "mock":
            if self.worker.measuring:
                self.worker.send(json.dumps({"cmd": "stop"}) + "\n")
            else:
                self.worker.send(
                    json.dumps({"cmd": "start", "mode": "continuous"}) + "\n"
                )
            return

        if self.btn_start.text() == "Start":
            self._single_shot_pending = False
            self.send_config()
            self.worker.send_start(
                mode="continuous",
                send_raw=self.send_raw_cb.isChecked(),
                channels=self._led_channels(),
                deadtime=self.deadtime_spin.value(),
                brightness_r=self.brightness_r.value(),
                brightness_g=self.brightness_g.value(),
                brightness_b=self.brightness_b.value(),
            )
            if self.mon_cb.isChecked():
                self.worker.send_monitor(enable=True)
        else:
            self.worker.send_stop()

    def _start_mock(self):
        self.worker = MockSerialWorker()
        self.worker.data_received.connect(self.on_data)
        self.worker.raw_data_received.connect(self.on_raw_data)
        self.worker.data_raw_received.connect(self.on_data_raw)
        self.worker.status_changed.connect(self.on_status)
        self.worker.config_received.connect(self.on_config)
        self.worker.monitor_received.connect(self.on_monitor_data)
        self.worker.connection_changed.connect(self.on_connection_changed)
        self.worker.start()
        self.send_config()
        self.worker.send(
            json.dumps(
                {
                    "cmd": "start",
                    "mode": "continuous",
                    "send_raw": 1 if self.send_raw_cb.isChecked() else 0,
                    "channels": self._led_channels(),
                    "deadtime": self.deadtime_spin.value(),
                    "brightness_r": self.brightness_r.value(),
                    "brightness_g": self.brightness_g.value(),
                    "brightness_b": self.brightness_b.value(),
                }
            )
            + "\n"
        )

    def send_led_intensity(self, color, value):
        pass

    def _check_heartbeat(self):
        if self.mode == "esp32" and self.connected and self.device_state != "idle":
            elapsed = time.time() - self.last_data_time
            if elapsed > 5.0:
                self.heartbeat.setStyleSheet("font-size: 20px; color: orange;")
            if elapsed > 15.0:
                self._disconnect()
                self.status.setText("Connection lost (timeout)")

    def on_data(self, key, val_ref, val_mA):
        self.last_data_time = time.time()
        if self.send_raw_cb.isChecked():
            return
        if key == "R":
            self.r.append(val_ref)
        elif key == "G":
            self.g.append(val_ref)
        elif key == "B":
            self.b.append(val_ref)

    def capture_baseline(self):
        if len(self.r) < 20:
            return

        self.base_r = sum(list(self.r)[-20:]) / 20
        self.base_g = sum(list(self.g)[-20:]) / 20
        self.base_b = sum(list(self.b)[-20:]) / 20

        self.line_base_r.setValue(self.base_r)
        self.line_base_g.setValue(self.base_g)
        self.line_base_b.setValue(self.base_b)

        self.line_base_r.show()
        self.line_base_g.show()
        self.line_base_b.show()

        self.baseline_ready = True
        self.filtered_score = 0.0
        self.state_window.clear()
        self.status.setText("Calibrated")

    def clear_plots(self):
        self.r.clear()
        self.g.clear()
        self.b.clear()
        self.raw_data.clear()
        self.monitor_buf.clear()
        for led in range(3):
            self._cycle_curves[led][0].setData([], [])
            self._cycle_curves[led][1].setData([], [])
            self._monitor_cycle[led] = ([], [])
        self._monitor_cycle_seen.clear()
        self.monitor_label.setText("")
        self.filtered_score = 0.0
        self.state_window.clear()
        self.big_score.setText("---")
        self.class_label.setText("WAITING")
        self.traffic.setStyleSheet("color: gray; font-size: 80px;")
        self.status.setText("Cleared")

    def compute_score(self, r, g, b):
        if not self.baseline_ready:
            return 0.0

        dr = abs(r - self.base_r) / (self.base_r if self.base_r != 0 else 1.0)
        dg = abs(g - self.base_g) / (self.base_g if self.base_g != 0 else 1.0)
        db = abs(b - self.base_b) / (self.base_b if self.base_b != 0 else 1.0)

        diff_percentage = ((dr + dg + db) / 3.0) * 100.0
        return diff_percentage

    def classify(self, score):
        if score < 5:
            return "CLEAR", "green"
        elif score < 15:
            return "SLIGHT", "yellow"
        else:
            return "DIRTY", "red"

    def update_loop(self):
        if not (self.r and self.g and self.b):
            return

        self.curve_r.setData(list(self.r))
        self.curve_g.setData(list(self.g))
        self.curve_b.setData(list(self.b))

        if not self.baseline_ready:
            self.class_label.setText("WAITING")
            self.big_score.setText("---")
            self.traffic.setStyleSheet("color: gray; font-size: 80px;")
            self.line_base_r.hide()
            self.line_base_g.hide()
            self.line_base_b.hide()
            return

        score_raw = self.compute_score(
            list(self.r)[-1], list(self.g)[-1], list(self.b)[-1]
        )

        self.filtered_score = (
            self.alpha * score_raw + (1 - self.alpha) * self.filtered_score
        )

        new_class, _ = self.classify(self.filtered_score)
        self.state_window.append(new_class)

        stable_class = max(set(self.state_window), key=self.state_window.count)
        self.stable_class = stable_class

        self.big_score.setText(f"{self.filtered_score:.1f}%")
        self.class_label.setText(self.stable_class)

        color = {"CLEAR": "green", "SLIGHT": "yellow", "DIRTY": "red"}.get(
            self.stable_class, "gray"
        )
        self.traffic.setStyleSheet(f"color: {color}; font-size: 80px;")

    def on_raw_data(self, led, ch0, ch1):
        self.last_data_time = time.time()
        ch0_ma = [v / ADC_FULL_SCALE * (ADC_VREF / R_SENSE) * 1000.0 for v in ch0]
        self.raw_data[led] = {"ch0": ch0, "ch1": ch1, "ch0_ma": ch0_ma}

    def on_data_raw(self, led, ch0, ch1, presamples):
        self.last_data_time = time.time()
        self._monitor_led = led
        key = ["R", "G", "B"][led]
        ch0_ma = [v / ADC_FULL_SCALE * (ADC_VREF / R_SENSE) * 1000.0 for v in ch0]
        self.raw_data[led] = {
            "ch0": ch0,
            "ch1": ch1,
            "ch0_ma": ch0_ma,
            "presamples": presamples,
        }

        samples_count = len(ch0) - presamples
        self.lbl_actual_presamples.setText(f"dark: {presamples}")
        self.lbl_actual_samples.setText(f"light: {samples_count}")

        if samples_count > 0:
            dark_ch0 = ch0[:presamples]
            dark_ch1 = ch1[:presamples]
            light_ch0 = ch0[presamples:]
            light_ch1 = ch1[presamples:]

            off_ch0 = sum(dark_ch0) / max(presamples, 1)
            off_ch1 = sum(dark_ch1) / max(presamples, 1)
            avg_light_ch0 = sum(light_ch0) / samples_count
            avg_light_ch1 = sum(light_ch1) / samples_count

            ch0_res = abs(avg_light_ch0 - off_ch0)
            ch1_res = abs(avg_light_ch1 - off_ch1)

            ref = ch1_res / ch0_res if ch0_res != 0 else 0.0
            curr = (ch0_res / ADC_FULL_SCALE) * (ADC_VREF / R_SENSE) * 1000.0

            if key == "R":
                self.r.append(ref)
            elif key == "G":
                self.g.append(ref)
            elif key == "B":
                self.b.append(ref)
        if self._single_shot_pending:
            self._single_shot_remaining -= 1
            if self._single_shot_remaining <= 0:
                self._single_shot_pending = False
                if self.worker:
                    self.worker.send_monitor(enable=False)

    def on_connection_changed(self, connected):
        self.connected = connected
        if connected:
            self.last_data_time = time.time()
            self.heartbeat.setStyleSheet("font-size: 20px; color: #00cc00;")
            self.btn_connect.setText("Disconnect")
            self.status.setText("Connected")
            self.btn_start.setEnabled(True)
            self.port_box.setEnabled(False)
            self.btn_refresh.setEnabled(False)
        else:
            self.heartbeat.setStyleSheet("font-size: 20px; color: red;")
            self.btn_connect.setText("Connect")
            self.status.setText("Disconnected")
            self.btn_start.setEnabled(False)
            self.btn_start.setText("Start")
            self.port_box.setEnabled(True)
            self.btn_refresh.setEnabled(True)
            self.worker = None

    def on_status(self, state):
        self.device_state = state
        self.last_data_time = time.time()
        if self.mode == "esp32":
            self.status.setText(state.capitalize())
        if state == "measuring":
            self.btn_start.setText("Stop")
        else:
            self.btn_start.setText("Start")

    def on_config(self, cfg):
        self.osr_box.setCurrentIndex(cfg.get("osr", 5))
        self.presamples_spin.setValue(cfg.get("presamples", 80))
        self.samples_spin.setValue(cfg.get("samples", 160))
        self._update_est_time()
        self.brightness_r.setValue(cfg.get("brightness_r", cfg.get("brightness", 1000)))
        self.brightness_b.setValue(cfg.get("brightness_b", cfg.get("brightness", 1000)))
        self.brightness_g.setValue(cfg.get("brightness_g", cfg.get("brightness", 1000)))
        ch = cfg.get("channels", 7)
        self.chk_r.setChecked(bool(ch & 1))
        self.chk_b.setChecked(bool(ch & 2))
        self.chk_g.setChecked(bool(ch & 4))
        if "deadtime" in cfg:
            self.deadtime_spin.setValue(cfg["deadtime"])
        if "send_raw" in cfg:
            self.send_raw_cb.setChecked(bool(cfg["send_raw"]))
        self.lbl_actual_presamples.setText(f"dark: {cfg.get('presamples', 80)}")
        self.lbl_actual_samples.setText(f"light: {cfg.get('samples', 160)}")

    def send_config(self):
        if not self.worker:
            return
        window = self.presamples_spin.value() + self.samples_spin.value()
        num_leds = bin(self._led_channels()).count("1")
        self.monitor_buf = deque(maxlen=window * max(num_leds, 1))
        self.worker.send_set(
            osr=self.osr_box.currentData(),
            presamples=self.presamples_spin.value(),
            samples=self.samples_spin.value(),
            deadtime=self.deadtime_spin.value(),
            brightness_r=self.brightness_r.value(),
            brightness_g=self.brightness_g.value(),
            brightness_b=self.brightness_b.value(),
            channels=self._led_channels(),
            send_raw=self.send_raw_cb.isChecked(),
        )

    def send_single(self):
        if not self.worker:
            return
        self._single_shot_pending = False
        self.raw_data.clear()
        self.send_config()
        self.worker.send_start(
            mode="single",
            send_raw=self.send_raw_cb.isChecked(),
            channels=self._led_channels(),
            deadtime=self.deadtime_spin.value(),
            brightness_r=self.brightness_r.value(),
            brightness_g=self.brightness_g.value(),
            brightness_b=self.brightness_b.value(),
        )
        if self.mon_cb.isChecked():
            self.worker.send_monitor(enable=True)
            self._single_shot_pending = True
            self._single_shot_remaining = bin(self._led_channels()).count("1")

    def _update_est_time(self):
        osr_val = 128 << self.osr_box.currentData()
        presamples = self.presamples_spin.value()
        samples = self.samples_spin.value()
        deadtime = self.deadtime_spin.value()
        channels = self._led_channels()
        num_leds = bin(channels).count("1")
        if num_leds == 0:
            self.lbl_est_time.setText("--")
            return
        sample_time_us = osr_val / 2
        total_samples_per_led = deadtime + presamples + 3 + deadtime + samples
        time_per_led_ms = total_samples_per_led * sample_time_us / 1000
        total_time_s = num_leds * time_per_led_ms / 1000
        self.lbl_est_time.setText(
            f"{time_per_led_ms:.0f}ms / LED  ({total_time_s:.1f}s total)"
        )

    def toggle_monitor(self, checked):
        if checked:
            self.monitor_plot.show()
            self.monitor_label.show()
            self.send_raw_cb.setChecked(True)
        else:
            self.monitor_plot.hide()
            self.monitor_label.hide()

    def on_monitor_data(self, ch0, ch1):
        self.last_data_time = time.time()
        conv = lambda v: v / 8388608.0 * (1.2 / 10.0) * 1000.0
        c0 = [conv(v) for v in ch0]
        c1 = [conv(v) for v in ch1]

        if self.device_state == "measuring":
            led = self._monitor_led
            self._monitor_cycle[led][0].extend(c0)
            self._monitor_cycle[led][1].extend(c1)
            self._monitor_cycle_seen.add(led)
            self._flush_monitor_cycle()
        else:
            for a, b in zip(c0, c1):
                self.monitor_buf.append((a, b))
            if self.monitor_buf:
                t = list(range(len(self.monitor_buf)))
                self._cycle_curves[0][0].setData(t, [p[0] for p in self.monitor_buf])
                self._cycle_curves[0][1].setData(t, [p[1] for p in self.monitor_buf])
                for led in (1, 2):
                    self._cycle_curves[led][0].setData([], [])
                    self._cycle_curves[led][1].setData([], [])
                self.monitor_label.setText(
                    f"Monitor — ch0 (colored), ch1 (gray) — {len(self.monitor_buf)} samples"
                )

    def _flush_monitor_cycle(self):
        num_leds = bin(self._led_channels()).count("1")
        if len(self._monitor_cycle_seen) < num_leds:
            return
        expected = self.presamples_spin.value() + self.samples_spin.value()
        if any(
            len(self._monitor_cycle[led][0]) < expected
            for led in self._monitor_cycle_seen
        ):
            return
        total = 0
        for led in (0, 1, 2):
            arr0 = self._monitor_cycle[led][0]
            arr1 = self._monitor_cycle[led][1]
            if not arr0:
                self._cycle_curves[led][0].setData([], [])
                self._cycle_curves[led][1].setData([], [])
                continue
            n = len(arr0)
            xs = list(range(total, total + n))
            self._cycle_curves[led][0].setData(xs, arr0)
            self._cycle_curves[led][1].setData(xs, arr1)
            total += n
        self.monitor_label.setText(
            f"Cycle — ch0 (colored), ch1 (gray) — {total} samples"
        )
        for led in range(3):
            self._monitor_cycle[led] = ([], [])
        self._monitor_cycle_seen.clear()

    def refresh_ports(self):
        prev = self.port_box.currentText()
        self.port_box.clear()
        try:
            preferred = []
            other = []
            for port in serial.tools.list_ports.comports():
                d = port.device
                if "ttyACM" in d or "ttyUSB" in d:
                    preferred.append(d)
                else:
                    other.append(d)
            for d in preferred + other:
                self.port_box.addItem(d)
            # auto-select preferred port, or restore previous selection
            if preferred:
                self.port_box.setCurrentText(preferred[0])
            elif prev:
                idx = self.port_box.findText(prev)
                if idx >= 0:
                    self.port_box.setCurrentIndex(idx)
        except Exception:
            self.port_box.addItem("Keine Ports")
