import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient


GENERAL_STATUS_NAMES = {
    0: "Normal",
    1: "Warning",
    2: "High Risk",
    3: "Critical",
}


def decode_signed_temperature(register_value):
    if register_value >= 32768:
        register_value -= 65536

    return register_value / 10


def read_and_display(client):
    response = client.read_holding_registers(
        address=0,
        count=9,
        device_id=1,
    )

    if response.isError():
        print(f"Register reading error: {response}")
        return

    registers = response.registers

    l1_current = registers[0] / 10
    cabinet_temperature = decode_signed_temperature(registers[1])
    surface_temperature = decode_signed_temperature(registers[2])
    humidity = registers[3] / 10

    overload_risk = registers[4]
    connection_risk = registers[5]
    insulation_risk = registers[6]
    arc_status = registers[7]
    general_status = registers[8]

    status_name = GENERAL_STATUS_NAMES.get(
        general_status,
        f"Unknown ({general_status})",
    )

    arc_text = "Detected" if arc_status == 1 else "Not detected"
    reading_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n--- SCADA Readout: {reading_time} ---")
    print(f"L1 current: {l1_current} A")
    print(f"Cabinet temperature: {cabinet_temperature} °C")
    print(f"Surface temperature: {surface_temperature} °C")
    print(f"Relative humidity: %{humidity}")
    print(f"Overload risk score: {overload_risk}/100")
    print(f"Connection risk score: {connection_risk}/100")
    print(f"Insulation risk score: {insulation_risk}/100")
    print(f"Arc status: {arc_text}")
    print(f"General status: {status_name}")


def main():
    client = ModbusTcpClient(
        host="127.0.0.1",
        port=5020,
        timeout=3,
    )

    if not client.connect():
        print("Could not connect to Modbus server.")
        raise SystemExit(1)

    print("Connected to Modbus server.")
    print("Press Ctrl+C to stop polling.")

    try:
        while True:
            read_and_display(client)
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nSCADA polling stopped.")

    finally:
        client.close()


if __name__ == "__main__":
    main()