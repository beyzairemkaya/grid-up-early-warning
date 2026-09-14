from pymodbus.client import ModbusTcpClient

def decode_signed_temperature(register_value):
    if register_value >= 32768:
        register_value -= 65536

    return register_value / 10

client = ModbusTcpClient(
    host="127.0.0.1",
    port=5020,
    timeout=3,
)

if not client.connect():
    print("Couldnt connect Modbus server.")
    raise SystemExit(1)

try:
    response = client.read_holding_registers(
        address=0,
        count=9,
        device_id=1,
    )

    if response.isError():
        print(f"Register reading error: {response}")

    else:
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

        print("\n--- SCADA Modbus Readout ---")
        print(f"L1 current: {l1_current} A")
        print(f"Cabinet temperature: {cabinet_temperature} °C")
        print(f"Surface temperature: {surface_temperature} °C")
        print(f"Relative humidity: %{humidity}")
        print(f"Overload risk score: {overload_risk}/100")
        print(f"Connection risk score: {connection_risk}/100")
        print(f"Insulation risk score: {insulation_risk}/100")
        print(f"Arc status: {arc_status}")
        print(f"General status: {general_status}")

finally:
    client.close()