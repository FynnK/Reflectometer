# backend/serial_worker.py

import re
import serial
import threading
from PyQt6.QtCore import QObject, pyqtSignal


class SerialWorker(QObject):
    # Sendet nun Key, Reflexionswert, mA-Wert
    data_received = pyqtSignal(str, float, float)

    def __init__(self, port, baud=115200):
        super().__init__()
        self.port = port
        self.baud = baud
        self.running = False

        # Angepasste Regex fängt jetzt sowohl den Faktor als auch den mA-Wert ein
        # Erwartet z.B.: "RED: 0.45 @ 12.5mA BLUE: 0.35 @ 14.2mA GREEN: 0.55 @ 11.1mA"
        self.log_regex = re.compile(
            r"RED:\s*([\d\.]+)\s*@\s*([\d\.]+)mA.*BLUE:\s*([\d\.]+)\s*@\s*([\d\.]+)mA.*GREEN:\s*([\d\.]+)\s*@\s*([\d\.]+)mA"
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
        if hasattr(self, "ser") and self.ser and self.ser.is_open:
            try:
                self.ser.write(msg.encode())
                self.ser.flush()
            except Exception as e:
                print(f"Fehler beim Senden: {e}")

    def loop(self):
        while self.running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                match = self.log_regex.search(line)
                if match:
                    ref_red = float(match.group(1))
                    ma_red = float(match.group(2))
                    
                    ref_blue = float(match.group(3))
                    ma_blue = float(match.group(4))
                    
                    ref_green = float(match.group(5))
                    ma_green = float(match.group(6))

                    self.data_received.emit("R", ref_red, ma_red)
                    self.data_received.emit("G", ref_green, ma_green)
                    self.data_received.emit("B", ref_blue, ma_blue)
            except Exception:
                pass