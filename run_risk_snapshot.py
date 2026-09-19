"""Replay synthetic CSV rows through one persistent engine into a Modbus snapshot.

Run this in one terminal; run the existing Modbus server with --snapshot-file
and the existing SCADA client in two other terminals.
"""

import argparse
import csv
import json
import os
import tempfile
import time
from pathlib import Path

from anomali_motoru_v2 import AnomaliMotoru, Okuma
from risk_snapshot_adapter import make_snapshot

try:
    from src.modbus.register_mapper import encode_snapshot
except ModuleNotFoundError as error:
    if error.name not in {"src", "src.modbus"}:
        raise
    from register_mapper import encode_snapshot


REQUIRED = (
    "current_r_A", "current_s_A", "current_t_A",
    "temp_r_C", "temp_s_C", "temp_t_C",
    "ambient_humidity_RH", "pd_charge_pC", "optical_lux",
)


def load_reading(row):
    missing = [name for name in REQUIRED if row.get(name) in (None, "")]
    if missing:
        raise ValueError(f"Missing CSV measurements: {', '.join(missing)}")
    return Okuma(
        zaman=row.get("timestamp"),
        i_r=float(row["current_r_A"]),
        i_s=float(row["current_s_A"]),
        i_t=float(row["current_t_A"]),
        sicaklik_r=float(row["temp_r_C"]),
        sicaklik_s=float(row["temp_s_C"]),
        sicaklik_t=float(row["temp_t_C"]),
        nem_rh=float(row["ambient_humidity_RH"]),
        pd_pc=float(row["pd_charge_pC"]),
        ark_lux=float(row["optical_lux"]),
        ortam_c=float(row["ambient_temp_C"]) if row.get("ambient_temp_C") else 25.0,
        v_r=float(row["voltage_r_V"]) if row.get("voltage_r_V") else 230.0,
        v_s=float(row["voltage_s_V"]) if row.get("voltage_s_V") else 230.0,
        v_t=float(row["voltage_t_V"]) if row.get("voltage_t_V") else 230.0,
    )


def write_snapshot(path, snapshot):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace within one directory so the Modbus server never reads partial JSON.
    fd, temp_path = tempfile.mkstemp(prefix=".snapshot-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(snapshot, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def main():
    parser = argparse.ArgumentParser(description="CSV -> risk engine -> Modbus snapshot")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--snapshot-file", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--pd-pulse-count", type=int, help="Simulated count when CSV lacks pd_pulse_count")
    parser.add_argument("--cabinet-temperature-c", type=float,
                        help="Simulated cabinet temperature when CSV lacks cabinet_temperature_c")
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("--interval must be non-negative")

    engine = AnomaliMotoru()  # Keep one instance for trend and overload history.
    with args.csv.open(newline="", encoding="utf-8-sig") as source:
        for number, row in enumerate(csv.DictReader(source), start=1):
            reading = load_reading(row)
            pulse = row.get("pd_pulse_count")
            if pulse in (None, ""):
                pulse = args.pd_pulse_count
            cabinet = row.get("cabinet_temperature_c")
            if cabinet in (None, ""):
                cabinet = args.cabinet_temperature_c
            if pulse is None or cabinet is None:
                parser.error("Supply pd_pulse_count and cabinet_temperature_c as CSV columns "
                             "or use --pd-pulse-count and --cabinet-temperature-c")
            result = engine.adim(reading)
            snapshot = make_snapshot(
                reading, result, pd_pulse_count=int(pulse),
                cabinet_temperature_c=float(cabinet),
                pd_critical_pc=engine.e.PD_KRITIK_PC,
            )
            # Use the existing mapper to validate the whole register contract.
            encode_snapshot(snapshot)
            write_snapshot(args.snapshot_file, snapshot)
            print(f"row={number} level={result.seviye} alarms={result.alarmlar} "
                  f"scores={snapshot['overload_risk']}/{snapshot['connection_risk']}/"
                  f"{snapshot['insulation_risk']} status={snapshot['general_status']}", flush=True)
            if engine.kilitli:
                print("Arc lock active; local protection is independent of this simulator.")
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
