import serial.tools.list_ports


def get_ports():
    return [p.device for p in serial.tools.list_ports.comports()]