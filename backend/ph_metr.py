import serial
import time

class pHMetr:
    def __init__(self, com):
        self.com = com
        self.ser = serial.Serial(self.com, 115200, timeout=1, parity=serial.PARITY_EVEN)

    def read_data(self):
        if self.ser and self.ser.is_open:
            text = chr(1) + "#0#0#0" + chr(3)
            self.ser.write(text.encode('utf-8'))

            time.sleep(0.1)

            read_text = self.ser.read(self.ser.in_waiting)
            ascii_val = ''.join(chr(line) for line in read_text)

            pH_place = ascii_val.find('pH')
            temp_place = ascii_val.find('°C')

            if pH_place != -1 and temp_place != -1:
                pH = float(ascii_val[pH_place - 6:pH_place - 1].replace(',', '.').strip())
                temp = float(ascii_val[temp_place - 6:temp_place - 1].replace(',', '.').strip())
                return pH, temp

        return 7.00, 22.50

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
