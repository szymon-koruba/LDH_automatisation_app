import serial.tools.list_ports


def get_com_ports():
    ports = serial.tools.list_ports.comports()
    port_list = [port.device for port in ports]
    if not port_list:
        return ["Brak portów"]
    return port_list

