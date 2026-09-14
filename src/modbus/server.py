import argparse

from pymodbus.server import StartTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice
from register_mapper import encode_snapshot


SCENARIOS = {
    "normal": {
        "current_l1_a": 318.0,
        "cabinet_temperature_c": 29.1,
        "surface_temperature_c": 50.3,
        "relative_humidity_pct": 50.9,
        "overload_risk": 10,
        "connection_risk": 8,
        "insulation_risk": 5,
        "arc_status": 0,
        "general_status": 0,
    },

    "arc": {
        "current_l1_a": 318.0,
        "cabinet_temperature_c": 29.1,
        "surface_temperature_c": 50.3,
        "relative_humidity_pct": 50.9,
        "overload_risk": 10,
        "connection_risk": 8,
        "insulation_risk": 5,
        "arc_status": 1,
        "general_status": 3,
    },
}


def create_device(register_values):
    return SimDevice(
        id=1,
        simdata=[
            SimData(
                address=0,
                values=register_values,
                datatype=DataType.REGISTERS,
                readonly=True,
            )
        ],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Grid Up Modbus TCP field module simulator"
    )

    parser.add_argument(
        "--scenario",
        choices=SCENARIOS.keys(),
        default="normal",
        help="Test scenario presented through Modbus",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    snapshot = SCENARIOS[args.scenario]
    register_values = encode_snapshot(snapshot)
    device = create_device(register_values)

    print(f"Active scenario: {args.scenario}")
    print("Modbus TCP server running at 127.0.0.1:5020")

    StartTcpServer(
        device,
        address=("127.0.0.1", 5020),
    )


if __name__ == "__main__":
    main()