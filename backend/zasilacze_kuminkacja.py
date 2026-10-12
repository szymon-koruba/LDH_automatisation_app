import serial
import time

class KoradKD3005P:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):

        self.ser = serial.Serial(port=port,baudrate=baudrate,bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,timeout=timeout)
        time.sleep(0.1)

    def send_cmd(self, cmd: str):
        self.ser.write(cmd.encode('ascii'))
        time.sleep(0.05)


    def set_voltage(self, voltage: float):
        cmd = f"VSET1:{voltage:05.2f}"
        self.send_cmd(cmd)


    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()