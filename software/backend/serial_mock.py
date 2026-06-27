# backend/serial_mock.py

import random
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class MockSerialWorker(QObject):
    # ÄNDERUNG: Signal sendet jetzt float statt int für die neue Skala
    data_received = pyqtSignal(str, float)

    def __init__(self):
        super().__init__()

        self.timer = QTimer()
        self.timer.timeout.connect(self.generate)

        # Startwerte als typische Reflexionsfaktoren (Verhältniswerte)
        self.r = 0.45
        self.g = 0.55
        self.b = 0.35

    def start(self):
        self.timer.start(50)

    def stop(self):
        self.timer.stop()

    def send(self, msg):
        print("MOCK:", msg)

    def generate(self):
        # Kleine Fließkomma-Schritte (Rauschen) generieren
        self.r += random.uniform(-0.01, 0.01)
        self.g += random.uniform(-0.01, 0.01)
        self.b += random.uniform(-0.01, 0.01)

        # Begrenzung auf ein realistisches Verhältnis (0.0 bis 2.0)
        self.r = max(0.0, min(2.0, self.r))
        self.g = max(0.0, min(2.0, self.g))
        self.b = max(0.0, min(2.0, self.b))

        # Daten an die Haupt-GUI emittieren
        self.data_received.emit("R", self.r)
        self.data_received.emit("G", self.g)
        self.data_received.emit("B", self.b)