from pymodbus.server import StartTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice


REGISTER_VALUES = [
    3180,  # Offset 0 / 40001: L1 akımı = 318.0 A
    291,   # Offset 1 / 40002: Kabin sıcaklığı = 29.1 °C
    503,   # Offset 2 / 40003: Yüzey sıcaklığı = 50.3 °C
    509,   # Offset 3 / 40004: Bağıl nem = %50.9
    35,    # Offset 4 / 40005: Aşırı yük risk skoru
    62,    # Offset 5 / 40006: Bağlantı risk skoru
    20,    # Offset 6 / 40007: İzolasyon risk skoru
    0,     # Offset 7 / 40008: Ark durumu
    1,     # Offset 8 / 40009: Genel durum
]


device = SimDevice(
    id=1,
    simdata=[
        SimData(
            address=0,
            values=REGISTER_VALUES,
            datatype=DataType.REGISTERS,
            readonly=True,
        )
    ],
)


if __name__ == "__main__":
    print("Modbus TCP server running at 127.0.0.1:5020", flush=True)
    StartTcpServer(device, address=("127.0.0.1", 5020))