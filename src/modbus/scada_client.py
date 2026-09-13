from pymodbus.client import ModbusTcpClient


client = ModbusTcpClient(
    host="127.0.0.1",
    port=5020,
    timeout=3,
)

if not client.connect():
    print("Modbus sunucusuna bağlanılamadı.")
    raise SystemExit(1)

try:
    response = client.read_holding_registers(
        address=0,
        count=9,
        device_id=1,
    )

    if response.isError():
        print(f"Register okuma hatası: {response}")

    else:
        registers = response.registers

        l1_current = registers[0] / 10
        cabinet_temperature = registers[1] / 10
        surface_temperature = registers[2] / 10
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