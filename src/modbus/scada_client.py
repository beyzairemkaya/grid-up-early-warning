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


def decode_registers(registers):
    if len(registers) < 15:
        raise ValueError(
            f"Expected 15 Modbus registers, received {len(registers)}."
        )

    return {
        "current_l1_a": registers[0] / 10,
        "current_l2_a": registers[1] / 10,
        "current_l3_a": registers[2] / 10,

        "cabinet_temperature_c": decode_signed_temperature(
            registers[3]
        ),
        "surface_temperature_l1_c": decode_signed_temperature(
            registers[4]
        ),
        "surface_temperature_l2_c": decode_signed_temperature(
            registers[5]
        ),
        "surface_temperature_l3_c": decode_signed_temperature(
            registers[6]
        ),

        "relative_humidity_pct": registers[7] / 10,

        "pd_index": registers[8] / 10,
        "pd_pulse_count": registers[9],

        "overload_risk": registers[10],
        "connection_risk": registers[11],
        "insulation_risk": registers[12],

        "arc_status": registers[13],
        "general_status": registers[14],
    }


def read_snapshot(client):
    response = client.read_holding_registers(
        address=0,
        count=15,
        device_id=1,
    )

    if response.isError():
        raise RuntimeError(
            f"Register reading error: {response}"
        )

    return decode_registers(response.registers)


def display_snapshot(snapshot):
    general_status = snapshot["general_status"]
    arc_status = snapshot["arc_status"]

    status_name = GENERAL_STATUS_NAMES.get(
        general_status,
        f"Unknown ({general_status})",
    )

    arc_text = (
        "Detected"
        if arc_status == 1
        else "Not detected"
    )

    reading_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(f"\n--- SCADA Readout: {reading_time} ---")

    print("\nElectrical measurements")
    print(f"L1 current: {snapshot['current_l1_a']} A")
    print(f"L2 current: {snapshot['current_l2_a']} A")
    print(f"L3 current: {snapshot['current_l3_a']} A")

    print("\nEnvironmental and thermal measurements")
    print(
        "Cabinet temperature: "
        f"{snapshot['cabinet_temperature_c']} °C"
    )
    print(
        "L1 surface temperature: "
        f"{snapshot['surface_temperature_l1_c']} °C"
    )
    print(
        "L2 surface temperature: "
        f"{snapshot['surface_temperature_l2_c']} °C"
    )
    print(
        "L3 surface temperature: "
        f"{snapshot['surface_temperature_l3_c']} °C"
    )
    print(
        "Relative humidity: "
        f"%{snapshot['relative_humidity_pct']}"
    )

    print("\nPartial discharge indicators")
    print(f"PD index: {snapshot['pd_index']}/100")
    print(
        f"PD pulse count: {snapshot['pd_pulse_count']}"
    )

    print("\nRisk assessment")
    print(
        "Overload risk score: "
        f"{snapshot['overload_risk']}/100"
    )
    print(
        "Connection risk score: "
        f"{snapshot['connection_risk']}/100"
    )
    print(
        "Insulation risk score: "
        f"{snapshot['insulation_risk']}/100"
    )
    print(f"Arc status: {arc_text}")
    print(f"General status: {status_name}")


def read_and_display(client):
    try:
        snapshot = read_snapshot(client)
        display_snapshot(snapshot)

    except (RuntimeError, ValueError) as error:
        print(error)


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