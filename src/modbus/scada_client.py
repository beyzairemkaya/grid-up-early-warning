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
        count=15,
        device_id=1,
    )

    if response.isError():
        print(f"Register reading error: {response}")
        return

    registers = response.registers

    # 40001–40003: Phase currents
    l1_current = registers[0] / 10
    l2_current = registers[1] / 10
    l3_current = registers[2] / 10

    # 40004–40007: Temperatures
    cabinet_temperature = decode_signed_temperature(registers[3])
    surface_temperature_l1 = decode_signed_temperature(registers[4])
    surface_temperature_l2 = decode_signed_temperature(registers[5])
    surface_temperature_l3 = decode_signed_temperature(registers[6])

    # 40008: Humidity
    humidity = registers[7] / 10

    # 40009–40010: Processed PD indicators
    pd_index = registers[8] / 10
    pd_pulse_count = registers[9]

    # 40011–40013: Risk scores
    overload_risk = registers[10]
    connection_risk = registers[11]
    insulation_risk = registers[12]

    # 40014–40015: Event and system state
    arc_status = registers[13]
    general_status = registers[14]

    status_name = GENERAL_STATUS_NAMES.get(
        general_status,
        f"Unknown ({general_status})",
    )

    arc_text = "Detected" if arc_status == 1 else "Not detected"
    reading_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n--- SCADA Readout: {reading_time} ---")

    print("\nElectrical measurements")
    print(f"L1 current: {l1_current} A")
    print(f"L2 current: {l2_current} A")
    print(f"L3 current: {l3_current} A")

    print("\nEnvironmental and thermal measurements")
    print(f"Cabinet temperature: {cabinet_temperature} °C")
    print(f"L1 surface temperature: {surface_temperature_l1} °C")
    print(f"L2 surface temperature: {surface_temperature_l2} °C")
    print(f"L3 surface temperature: {surface_temperature_l3} °C")
    print(f"Relative humidity: %{humidity}")

    print("\nPartial discharge indicators")
    print(f"PD index: {pd_index}/100")
    print(f"PD pulse count: {pd_pulse_count}")

    print("\nRisk assessment")
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