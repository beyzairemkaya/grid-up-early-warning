import argparse
import json
from pathlib import Path

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
def load_snapshot(file_path):
    with Path(file_path).open("r", encoding="utf-8") as file:
        snapshot = json.load(file)

    if not isinstance(snapshot, dict):
        raise ValueError("Snapshot file must contain a JSON object.")

    return snapshot
def create_snapshot_refresh_action(snapshot_file):
    async def refresh_registers(
        function_code,
        start_address,
        address,
        count,
        current_registers,
        set_values,
    ):
        # Yalnızca holding register okuma isteğinde güncelle.
        if function_code != 3 or set_values is not None:
            return None

        try:
            snapshot = load_snapshot(snapshot_file)
            new_register_values = encode_snapshot(snapshot)

            current_registers[:len(new_register_values)] = new_register_values

        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            print(f"Snapshot could not be refreshed: {error}")

        return None

    return refresh_registers


def create_device(register_values, snapshot_file=None):
    refresh_action = None

    if snapshot_file is not None:
        refresh_action = create_snapshot_refresh_action(snapshot_file)
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
        action=refresh_action,
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

    parser.add_argument(
        "--snapshot-file",
        type=Path,
        help="Read the Modbus values from a JSON snapshot file",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.snapshot_file:
        snapshot = load_snapshot(args.snapshot_file)
        source_description = f"snapshot file: {args.snapshot_file}"
    else:
        snapshot = SCENARIOS[args.scenario]
        source_description = f"built-in scenario: {args.scenario}"

    register_values = encode_snapshot(snapshot)
    device = create_device(register_values, args.snapshot_file)

    print(f"Active source: {source_description}")
    print("Modbus TCP server running at 127.0.0.1:5020")

    StartTcpServer(
        device,
        address=("127.0.0.1", 5020),
    )


if __name__ == "__main__":
    main()