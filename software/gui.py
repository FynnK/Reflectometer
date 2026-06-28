# gui.py

from PyQt6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSlider
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

        self.setWindowTitle("Optical System - Dual Axis Plot")
        self.resize(1200, 850)

        self.worker = None
        self.mode = "mock"

        self.max_points = 150
        
        # Deques für die Reflexionswerte (Linke Achse)
        self.r = deque(maxlen=self.max_points)
        self.g = deque(maxlen=self.max_points)
        self.b = deque(maxlen=self.max_points)

        # Deques für die Stromwerte in mA (Rechte Achse)
        self.curr_r = deque(maxlen=self.max_points)
        self.curr_g = deque(maxlen=self.max_points)
        self.curr_b = deque(maxlen=self.max_points)

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

        # LED STEUERUNG (SLIDER)
        led_layout = QHBoxLayout()
        led_layout.addWidget(QLabel("<b>LED-Intensität:</b>"))

        # Roter Slider
        led_layout.addWidget(QLabel("R:"))
        self.slider_r = QSlider(Qt.Orientation.Horizontal)
        self.slider_r.setRange(0, 255)
        self.slider_r.setValue(128)
        self.slider_r.valueChanged.connect(lambda val: self.send_led_intensity("R", val))
        self.lbl_val_r = QLabel("128")
        led_layout.addWidget(self.slider_r)
        led_layout.addWidget(self.lbl_val_r)

        # Grüner Slider
        led_layout.addWidget(QLabel("G:"))
        self.slider_g = QSlider(Qt.Orientation.Horizontal)
        self.slider_g.setRange(0, 255)
        self.slider_g.setValue(128)
        self.slider_g.valueChanged.connect(lambda val: self.send_led_intensity("G", val))
        self.lbl_val_g = QLabel("128")
        led_layout.addWidget(self.slider_g)
        led_layout.addWidget(self.lbl_val_g)

        # Blauer Slider
        led_layout.addWidget(QLabel("B:"))
        self.slider_b = QSlider(Qt.Orientation.Horizontal)
        self.slider_b.setRange(0, 255)
        self.slider_b.setValue(128)
        self.slider_b.valueChanged.connect(lambda val: self.send_led_intensity("B", val))
        self.lbl_val_b = QLabel("128")
        led_layout.addWidget(self.slider_b)
        led_layout.addWidget(self.lbl_val_b)
        layout.addLayout(led_layout)

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

        # ==========================================================
        # PLOT KONFIGURATION MIT ZWEI Y-ACHSEN
        # ==========================================================
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True)
        
        # Linke Achse: Reflexion
        self.plot.setYRange(0.0, 1.5)
        self.plot.setLabel('left', 'Reflexion (Verhältniswert)', colors='#FFFFFF')
        self.plot.setLabel('bottom', 'Messpunkte')

        plot_item = self.plot.plotItem

        # Rechte Achse über die interne API erstellen
        self.right_view = pg.ViewBox()
        plot_item.scene().addItem(self.right_view)
        
        # Achsen-Item auf der rechten Seite registrieren
        self.right_axis = plot_item.getAxis('right')
        self.right_axis.linkToView(self.right_view)
        plot_item.showAxis('right')
        
        # Verknüpft die X-Achse der rechten ViewBox mit der linken ViewBox
        self.right_view.setXLink(plot_item.getViewBox())
        self.plot.setLabel('right', 'LED-Strom (mA)', colors='#999999')

        # Dynamische Skalierung der rechten Achsensicht bei Größenänderung
        def update_views():
            self.right_view.setGeometry(plot_item.getViewBox().sceneBoundingRect())
            self.right_view.linkedViewChanged(plot_item.getViewBox(), self.right_view.XAxis)
        
        # Aufruf über .getViewBox() statt .viewBox gelöst
        plot_item.getViewBox().sigResized.connect(update_views)

        # Kurven für linke Achse (Reflexion - durchgezogen)
        self.curve_r = self.plot.plot(pen=pg.mkPen('r', width=1.5))
        self.curve_g = self.plot.plot(pen=pg.mkPen('g', width=1.5))
        self.curve_b = self.plot.plot(pen=pg.mkPen('b', width=1.5))

        # Kurven für rechte Achse (Strom mA - gepunktet)
        self.curve_curr_r = pg.PlotCurveItem(pen=pg.mkPen((255, 50, 50), width=1.5, style=Qt.PenStyle.DotLine))
        self.curve_curr_g = pg.PlotCurveItem(pen=pg.mkPen((50, 255, 50), width=1.5, style=Qt.PenStyle.DotLine))
        self.curve_curr_b = pg.PlotCurveItem(pen=pg.mkPen((50, 50, 255), width=1.5, style=Qt.PenStyle.DotLine))
        self.right_view.addItem(self.curve_curr_r)
        self.right_view.addItem(self.curve_curr_g)
        self.right_view.addItem(self.curve_curr_b)
        
        # Fester Bereich für die Stromwerte
        self.right_view.setYRange(0.0, 30.0)

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
            self.line_base_r.hide()
            self.line_base_g.hide()
            self.line_base_b.hide()
            self.baseline_ready = False
            return

        if self.mode == "mock":
            self.worker = MockSerialWorker()
        else:
            port = self.port_box.currentText()
            self.worker = SerialWorker(port)

        self.worker.data_received.connect(self.on_data)
        self.worker.start()
        self.status.setText("Running")

        self.send_led_intensity("R", self.slider_r.value())
        self.send_led_intensity("G", self.slider_g.value())
        self.send_led_intensity("B", self.slider_b.value())

    def send_led_intensity(self, color, value):
        if color == "R":
            self.lbl_val_r.setText(str(value))
        elif color == "G":
            self.lbl_val_g.setText(str(value))
        elif color == "B":
            self.lbl_val_b.setText(str(value))

        if self.worker:
            cmd = f"SET_LED:{color}:{value}\n"
            self.worker.send(cmd)

    def on_data(self, key, val_ref, val_mA):
        if key == "R":
            self.r.append(val_ref)
            self.curr_r.append(val_mA)
        elif key == "G":
            self.g.append(val_ref)
            self.curr_g.append(val_mA)
        elif key == "B":
            self.b.append(val_ref)
            self.curr_b.append(val_mA)

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

        # Linke Achse aktualisieren
        self.curve_r.setData(list(self.r))
        self.curve_g.setData(list(self.g))
        self.curve_b.setData(list(self.b))

        # Rechte Achse aktualisieren
        if self.curr_r and self.curr_g and self.curr_b:
            self.curve_curr_r.setData(list(self.curr_r))
            self.curve_curr_g.setData(list(self.curr_g))
            self.curve_curr_b.setData(list(self.curr_b))

        if not self.baseline_ready:
            self.class_label.setText("WAITING")
            self.big_score.setText("---")
            self.traffic.setStyleSheet("color: gray; font-size: 80px;")
            self.line_base_r.hide()
            self.line_base_g.hide()
            self.line_base_b.hide()
            return

        score_raw = self.compute_score(list(self.r)[-1], list(self.g)[-1], list(self.b)[-1])

        self.filtered_score = (
            self.alpha * score_raw +
            (1 - self.alpha) * self.filtered_score
        )

        new_class, _ = self.classify(self.filtered_score)
        self.state_window.append(new_class)

        stable_class = max(set(self.state_window), key=self.state_window.count)
        self.stable_class = stable_class

        self.big_score.setText(f"{self.filtered_score:.1f}%")
        self.class_label.setText(self.stable_class)

        color = {"CLEAR": "green", "SLIGHT": "yellow", "DIRTY": "red"}.get(self.stable_class, "gray")
        self.traffic.setStyleSheet(f"color: {color}; font-size: 80px;")

    def refresh_ports(self):
        self.port_box.clear()
        try:
            for port in serial.tools.list_ports.comports():
                self.port_box.addItem(port.device)
        except Exception:
            self.port_box.addItem("Keine Ports")