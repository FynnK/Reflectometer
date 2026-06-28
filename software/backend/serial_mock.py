# backend/serial_mock.py

import random
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class MockSerialWorker(QObject):
    data_received = pyqtSignal(str, float, float)

    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.generate)

        # Startwerte Reflexion
        self.r = 0.45
        self.g = 0.55
        self.b = 0.35

        # Startwerte Stromstärke in mA
        self.ma_r = 15.0
        self.ma_g = 14.2
        self.ma_b = 16.5

    def start(self):
        self.timer.start(50)

    def stop(self):
        self.timer.stop()

    def send(self, msg):
        print("MOCK:", msg.strip())
        # Optional: Hier auf die Schieberegler reagieren, um die simulierten mA-Werte zu ändern
        try:
            parts = msg.strip().split(':')
            if len(parts) == 3 and parts[0] == "SET_LED":
                color = parts[1]
                val = float(parts[2])
                # Wandelt 0-255 grob in 0-25mA um
                simulated_ma = (val / 255.0) * 25.0
                if color == "R": self.ma_r = simulated_ma
                elif color == "G": self.ma_g = simulated_ma
                elif color == "B": self.ma_b = simulated_ma
        except Exception:
            pass

    def generate(self):
        # Leichtes Rauschen hinzufügen
        self.r = max(0.0, min(2.0, self.r + random.uniform(-0.01, 0.01)))
        self.g = max(0.0, min(2.0, self.g + random.uniform(-0.01, 0.01)))
        self.b = max(0.0, min(2.0, self.b + random.uniform(-0.01, 0.01)))

        # Rauschen auf die simulierten mA-Werte addieren
        cur_r = max(0.0, min(30.0, self.ma_r + random.uniform(-0.1, 0.1)))
        cur_g = max(0.0, min(30.0, self.ma_g + random.uniform(-0.1, 0.1)))
        cur_b = max(0.0, min(30.0, self.ma_b + random.uniform(-0.1, 0.1)))

        self.data_received.emit("R", self.r, cur_r)
        self.data_received.emit("G", self.g, cur_g)
        self.data_received.emit("B", self.b, cur_b)