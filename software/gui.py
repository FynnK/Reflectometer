# gui.py

from PyQt6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
import pyqtgraph as pg
from collections import deque
import serial.tools.list_ports

from backend.serial_mock import MockSerialWorker
from backend.serial_worker import SerialWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Optical System - ESP32 Native Scale")
        self.resize(1200, 750)

        self.worker = None
        self.mode = "mock"

        self.max_points = 150
        self.r = deque(maxlen=self.max_points)
        self.g = deque(maxlen=self.max_points)
        self.b = deque(maxlen=self.max_points)

        self.base_r = None
        self.base_g = None
        self.base_b = None
        self.baseline_ready = False

        self.alpha = 0.4
        self.filtered_score = 0.0
        self.stable_class = "WAITING"
        self.state_window = deque(maxlen=7)

        # UI LAYOUT
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout()
        root.setLayout(layout)

        # TOP BAR
        top = QHBoxLayout()

        self.mode_box = QComboBox()
        self.mode_box.addItems(["mock", "esp32"])
        self.mode_box.currentTextChanged.connect(self.set_mode)

        self.port_box = QComboBox()
        self.refresh_ports()

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.toggle)

        self.btn_calibrate = QPushButton("Calibrate")
        self.btn_calibrate.clicked.connect(self.capture_baseline)

        self.status = QLabel("Idle")

        top.addWidget(QLabel("Mode:"))
        top.addWidget(self.mode_box)
        top.addWidget(QLabel("Port:"))
        top.addWidget(self.port_box)
        top.addWidget(self.btn_start)
        top.addWidget(self.btn_calibrate)
        top.addWidget(self.status)

        layout.addLayout(top)

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

        # PLOT CONFIGURATION
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        
        # ÄNDERUNG: Da der ESP32 Verhältnisse liefert, ändern wir das Y-Limit.
        # 0.0 bis 2.0 deckt die meisten Reflexionskurven perfekt ab.
        self.plot.setYRange(0.0, 2.0)

        self.curve_r = self.plot.plot(pen="r")
        self.curve_g = self.plot.plot(pen="g")
        self.curve_b = self.plot.plot(pen="b")

        layout.addWidget(self.plot)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(50)

    def set_mode(self, mode):
        self.mode = mode

    def toggle(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
            self.status.setText("Stopped")
            return

        if self.mode == "mock":
            self.worker = MockSerialWorker()
        else:
            port = self.port_box.currentText()
            self.worker = SerialWorker(port)

        self.worker.data_received.connect(self.on_data)
        self.worker.start()
        self.status.setText("Running")

    def on_data(self, key, value):
        if key == "R":
            self.r.append(value)
        elif key == "G":
            self.g.append(value)
        elif key == "B":
            self.b.append(value)

    def capture_baseline(self):
        if len(self.r) < 20:
            return

        self.base_r = sum(list(self.r)[-20:]) / 20
        self.base_g = sum(list(self.g)[-20:]) / 20
        self.base_b = sum(list(self.b)[-20:]) / 20

        self.baseline_ready = True
        self.filtered_score = 0.0
        self.state_window.clear()

        self.status.setText("Calibrated")

    # =========================
    # NEUE SCORE-BERECHNUNG
    # =========================
    def compute_score(self, r, g, b):
        if not self.baseline_ready:
            return 0.0

        # Berechnet die relative Abweichung zum Kalibrierungs-Zustand.
        # Wenn der aktuelle Wert stark von der Basislinie abweicht, steigt der Score.
        dr = abs(r - self.base_r) / (self.base_r if self.base_r != 0 else 1.0)
        dg = abs(g - self.base_g) / (self.base_g if self.base_g != 0 else 1.0)
        db = abs(b - self.base_b) / (self.base_b if self.base_b != 0 else 1.0)

        # Durchschnittliche relative Abweichung in Prozent (Multiplikation mit 100)
        # Ein Score von z.B. 15% bedeutet, dass sich die Werte im Schnitt um 15% verändert haben.
        diff_percentage = ((dr + dg + db) / 3.0) * 100.0
        return diff_percentage

    def classify(self, score):
        # Die Schwellenwerte können je nach Empfindlichkeit eures Setups angepasst werden.
        if score < 5:
            return "CLEAR", "green"
        elif score < 15:
            return "SLIGHT", "yellow"
        else:
            return "DIRTY", "red"

    def update_loop(self):
        if not (self.r and self.g and self.b):
            return

        r = list(self.r)
        g = list(self.g)
        b = list(self.b)

        self.curve_r.setData(r)
        self.curve_g.setData(g)
        self.curve_b.setData(b)

        if not self.baseline_ready:
            self.class_label.setText("WAITING")
            self.big_score.setText("---")
            self.traffic.setStyleSheet("color: gray; font-size: 80px;")
            return

        score_raw = self.compute_score(r[-1], g[-1], b[-1])

        self.filtered_score = (
            self.alpha * score_raw +
            (1 - self.alpha) * self.filtered_score
        )

        new_class, _ = self.classify(self.filtered_score)
        self.state_window.append(new_class)

        stable_class = max(
            set(self.state_window),
            key=self.state_window.count
        )
        self.stable_class = stable_class

        self.big_score.setText(f"{self.filtered_score:.1f}%")
        self.class_label.setText(self.stable_class)

        color = {
            "CLEAR": "green",
            "SLIGHT": "yellow",
            "DIRTY": "red"
        }.get(self.stable_class, "gray")

        self.traffic.setStyleSheet(f"color: {color}; font-size: 80px;")

    def refresh_ports(self):
        self.port_box.clear()
        try:
            for port in serial.tools.list_ports.comports():
                self.port_box.addItem(port.device)
        except Exception:
            self.port_box.addItem("Keine Ports")