# backend/serial_worker.py

import re
import serial
import threading
from PyQt6.QtCore import QObject, pyqtSignal


class SerialWorker(QObject):
    # ÄNDERUNG: Wir senden jetzt float statt int für die präzisen Sensorwerte
    data_received = pyqtSignal(str, float)

    def __init__(self, port, baud=115200):
        super().__init__()
        self.port = port
        self.baud = baud
        self.running = False

        # Regex matcht die ESP_LOGI-Zeile des ESP32
        self.log_regex = re.compile(
            r"RED:\s*([\d\.]+)\s*@.*BLUE:\s*([\d\.]+)\s*@.*GREEN:\s*([\d\.]+)"
        )

    def start(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=1)
        self.running = True

        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, "ser"):
            self.ser.close()

    def send(self, msg):
        if hasattr(self, "ser"):
            self.ser.write(msg.encode())

    def loop(self):
        while self.running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                match = self.log_regex.search(line)
                if match:
                    # Werte direkt als originale Floats extrahieren (z.B. 0.45)
                    ref_red = float(match.group(1))
                    ref_blue = float(match.group(2))
                    ref_green = float(match.group(3))

                    # Direkt an die GUI weiterleiten
                    self.data_received.emit("R", ref_red)
                    self.data_received.emit("G", ref_green)
                    self.data_received.emit("B", ref_blue)

            except Exception:
                pass

    def send(self, msg):
        if hasattr(self, "ser") and self.ser and self.ser.is_open:
            try:
                self.ser.write(msg.encode())
                self.ser.flush() # Erzwingt das sofortige Senden der Daten
            except Exception as e:
                print(f"Fehler beim Senden: {e}")