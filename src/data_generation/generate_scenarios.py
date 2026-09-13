"""Generate reproducible synthetic switchboard telemetry scenarios.

This generator is a prototype test harness, not a substitute for field data.
It produces time-series runs for normal operation, overload, loose/high-
resistance connection, insulation/partial-discharge risk, combined faults,
and direct arc events.

The output contains sensor-like telemetry and ground-truth flags. It does not
contain model scores or threshold outputs; those must be produced separately
by the risk engine.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


SEED = 20260913
SAMPLE_MINUTES = 5
STEPS_PER_RUN = 24 * 60 // SAMPLE_MINUTES
START_TIME = datetime(2026, 1, 1, 0, 0, 0)

# These counts are for prototype coverage, not estimates of real fault rates.
SCENARIO_COUNTS = {
    "normal": 20,
    "overload": 10,
    "connection_fault": 10,
    "insulation_risk": 10,
    "combined": 5,
    "arc": 5,
}

FIELDNAMES = [
    "timestamp",
    "run_id",
    "split",
    "scenario_label",
    "event_stage",
    "rated_current_a",
    "current_l1_a",
    "current_l2_a",
    "current_l3_a",
    "cabinet_temperature_c",
    "surface_temperature_l1_c",
    "surface_temperature_l2_c",
    "surface_temperature_l3_c",
    "relative_humidity_pct",
    "pd_index",
    "pd_pulse_count",
    "arc_status",
    "overload_flag",
    "connection_fault_flag",
    "insulation_risk_flag",
]


@dataclass(frozen=True)
class RunSpec:
    """Definition of one independent time-series experiment."""

    scenario: str
    split: str


@dataclass
class EventWindow:
    """Start, end, and recovery positions for one injected event."""

    start: int
    end: int
    ramp_steps: int
    recovery_steps: int = 18

    def active(self, step: int) -> bool:
        return self.start <= step < self.end

    def recovering(self, step: int) -> bool:
        return self.end <= step < self.end + self.recovery_steps

    def progress(self, step: int) -> float:
        if step < self.start:
            return 0.0
        if step >= self.end:
            return 0.0
        return min(1.0, (step - self.start + 1) / self.ramp_steps)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def make_split_labels(count: int) -> list[str]:
    """Create run-level splits while keeping every small class in each split."""

    if count < 3:
        raise ValueError("Each scenario requires at least three runs.")

    validation_count = max(1, int(count * 0.15))
    test_count = max(1, int(count * 0.15))
    train_count = count - validation_count - test_count

    return (
        ["train"] * train_count
        + ["validation"] * validation_count
        + ["test"] * test_count
    )


def build_run_specs(rng: random.Random) -> list[RunSpec]:
    specs: list[RunSpec] = []

    for scenario, count in SCENARIO_COUNTS.items():
        splits = make_split_labels(count)
        rng.shuffle(splits)
        specs.extend(RunSpec(scenario=scenario, split=split) for split in splits)

    rng.shuffle(specs)
    return specs


def random_event_window(
    rng: random.Random,
    *,
    start_min: int = 72,
    start_max: int = 180,
    duration_min: int = 24,
    duration_max: int = 72,
) -> EventWindow:
    start = rng.randint(start_min, start_max)
    duration = rng.randint(duration_min, duration_max)
    return EventWindow(
        start=start,
        end=min(STEPS_PER_RUN - 20, start + duration),
        ramp_steps=rng.randint(3, 9),  # 15-45 minutes at 5-minute sampling.
    )


def event_stage(
    step: int,
    windows: list[EventWindow],
    *,
    arc_active: bool,
) -> str:
    if arc_active:
        return "critical"

    active_windows = [window for window in windows if window.active(step)]
    if active_windows:
        if any(window.progress(step) < 1.0 for window in active_windows):
            return "developing"
        return "critical"

    if any(window.recovering(step) for window in windows):
        return "recovery"

    return "normal"


def generate_run(
    run_number: int,
    spec: RunSpec,
    rng: random.Random,
) -> list[dict[str, object]]:
    """Generate one independent 24-hour time series."""

    actual_scenario = spec.scenario
    if spec.scenario == "combined":
        actual_scenario = rng.choice(
            ["combined_overload_connection", "combined_connection_insulation"]
        )

    has_overload = actual_scenario in {"overload", "combined_overload_connection"}
    has_connection = actual_scenario in {
        "connection_fault",
        "combined_overload_connection",
        "combined_connection_insulation",
    }
    has_insulation = actual_scenario in {
        "insulation_risk",
        "combined_connection_insulation",
    }
    has_arc = actual_scenario == "arc"

    overload_window = random_event_window(rng) if has_overload else None
    connection_window = random_event_window(rng) if has_connection else None
    insulation_window = (
        random_event_window(
            rng,
            start_min=48,
            start_max=120,
            duration_min=96,
            duration_max=150,
        )
        if has_insulation
        else None
    )
    arc_step = rng.randint(96, STEPS_PER_RUN - 36) if has_arc else None

    rated_current = rng.choice([160.0, 250.0, 400.0, 600.0])
    heat_gain = rng.uniform(28.0, 38.0)
    phase_heat_gains = [heat_gain * rng.uniform(0.92, 1.08) for _ in range(3)]
    thermal_alpha = rng.uniform(0.09, 0.20)
    base_cabinet_temperature = rng.uniform(24.0, 30.0)
    daily_temperature_amplitude = rng.uniform(2.0, 4.5)

    overload_ratio = rng.uniform(1.15, 1.50)
    connection_heat_gain = rng.uniform(12.0, 50.0)
    connection_phase = rng.randrange(3)
    insulation_humidity_target = rng.uniform(75.0, 96.0)

    # Normal operation may still include nuisance conditions. These make the
    # threshold evaluation less circular: a brief current peak, high humidity,
    # or one PD-like switching transient must not automatically become a fault.
    transient_current_start = rng.randint(30, STEPS_PER_RUN - 30)
    transient_current_duration = rng.randint(1, 2)
    transient_current_ratio = rng.uniform(1.02, 1.22)
    has_transient_current = rng.random() < 0.35

    humidity_excursion_start = rng.randint(30, STEPS_PER_RUN - 60)
    humidity_excursion_duration = rng.randint(12, 36)
    humidity_excursion_target = rng.uniform(75.0, 90.0)
    has_humidity_excursion = rng.random() < 0.30

    pd_transient_step = rng.randint(30, STEPS_PER_RUN - 30)
    has_pd_transient = rng.random() < 0.40

    load_ratio = rng.uniform(0.35, 0.60)
    cabinet_temperature = base_cabinet_temperature
    relative_humidity = rng.uniform(45.0, 65.0)
    surface_temperatures = [
        cabinet_temperature + rng.uniform(3.0, 7.0) for _ in range(3)
    ]

    start_time = START_TIME + timedelta(days=run_number - 1)
    rows: list[dict[str, object]] = []

    for step in range(STEPS_PER_RUN):
        timestamp = start_time + timedelta(minutes=step * SAMPLE_MINUTES)
        hour = timestamp.hour + timestamp.minute / 60.0

        # Smooth daily load profile plus a small random walk. Independent random
        # rows are intentionally avoided because electrical loads have memory.
        daily_load_target = (
            0.50
            + 0.16 * math.sin(2.0 * math.pi * (hour - 8.0) / 24.0)
            + 0.05 * math.sin(4.0 * math.pi * hour / 24.0)
        )
        load_ratio += 0.18 * (daily_load_target - load_ratio)
        load_ratio += rng.gauss(0.0, 0.012)
        load_ratio = clamp(load_ratio, 0.18, 0.88)

        overload_active = bool(overload_window and overload_window.active(step))
        connection_active = bool(
            connection_window and connection_window.active(step)
        )
        insulation_active = bool(
            insulation_window and insulation_window.active(step)
        )
        arc_active = step == arc_step

        effective_load_ratio = load_ratio
        if overload_active and overload_window:
            progress = overload_window.progress(step)
            effective_load_ratio += progress * (overload_ratio - load_ratio)
        elif (
            has_transient_current
            and transient_current_start
            <= step
            < transient_current_start + transient_current_duration
        ):
            effective_load_ratio = max(
                effective_load_ratio, transient_current_ratio
            )

        phase_offsets = [rng.gauss(0.0, 0.015) for _ in range(3)]
        phase_currents = [
            max(
                0.0,
                rated_current
                * effective_load_ratio
                * (1.0 + phase_offset)
                + rng.gauss(0.0, rated_current * 0.004),
            )
            for phase_offset in phase_offsets
        ]

        # Pano içi sıcaklığı yavaş değişen bir günlük çevrim olarak üretiyoruz.
        cabinet_target = (
            base_cabinet_temperature
            + daily_temperature_amplitude
            * math.sin(2.0 * math.pi * (hour - 8.0) / 24.0)
        )
        if insulation_active:
            cabinet_target -= rng.uniform(0.5, 1.5)
        cabinet_temperature += 0.10 * (cabinet_target - cabinet_temperature)
        cabinet_temperature += rng.gauss(0.0, 0.05)
        cabinet_temperature = clamp(cabinet_temperature, 15.0, 45.0)

        # Relative humidity changes smoothly and usually moves inversely to
        # cabinet temperature. High humidity alone does not create a fault.
        humidity_target = 57.0 - 1.25 * (
            cabinet_temperature - base_cabinet_temperature
        )
        if insulation_active and insulation_window:
            progress = insulation_window.progress(step)
            humidity_target += progress * (
                insulation_humidity_target - humidity_target
            )
        elif (
            has_humidity_excursion
            and humidity_excursion_start
            <= step
            < humidity_excursion_start + humidity_excursion_duration
        ):
            humidity_target = humidity_excursion_target
        relative_humidity += 0.08 * (humidity_target - relative_humidity)
        relative_humidity += rng.gauss(0.0, 0.25)
        relative_humidity = clamp(relative_humidity, 30.0, 98.0)

        # Surface temperature follows a thermal target with lag. Overload heats
        # all phases through I^2; a connection fault adds heat to one local phase.
        for phase_index in range(3):
            normalized_current = phase_currents[phase_index] / rated_current
            thermal_target = (
                cabinet_temperature
                + phase_heat_gains[phase_index] * normalized_current**2
            )

            if (
                connection_active
                and connection_window
                and phase_index == connection_phase
            ):
                thermal_target += (
                    connection_heat_gain * connection_window.progress(step)
                )

            surface_temperatures[phase_index] += thermal_alpha * (
                thermal_target - surface_temperatures[phase_index]
            )
            surface_temperatures[phase_index] += rng.gauss(0.0, 0.12)
            surface_temperatures[phase_index] = clamp(
                surface_temperatures[phase_index], 15.0, 140.0
            )

        # PD is represented as a synthetic, dimensionless index. It is not
        # labelled as pC because an HFCT alone does not provide calibrated pC.
        pd_mean = rng.uniform(1.0, 5.0)
        if insulation_active and insulation_window:
            progress = insulation_window.progress(step)
            humidity_effect = max(0.0, relative_humidity - 70.0) * 0.7
            pd_mean += progress * rng.uniform(12.0, 55.0) + humidity_effect
        elif has_pd_transient and step == pd_transient_step:
            pd_mean += rng.uniform(15.0, 38.0)

        pd_index = clamp(rng.gauss(pd_mean, max(1.0, pd_mean * 0.10)), 0.0, 100.0)
        pulse_mean = 1.0 + pd_index * 0.65
        pd_pulse_count = max(
            0,
            round(rng.gauss(pulse_mean, max(1.0, math.sqrt(pulse_mean)))),
        )

        windows = [
            window
            for window in (overload_window, connection_window, insulation_window)
            if window is not None
        ]
        stage = event_stage(step, windows, arc_active=arc_active)

        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "run_id": f"run_{run_number:03d}",
                "split": spec.split,
                "scenario_label": actual_scenario,
                "event_stage": stage,
                "rated_current_a": round(rated_current, 1),
                "current_l1_a": round(phase_currents[0], 2),
                "current_l2_a": round(phase_currents[1], 2),
                "current_l3_a": round(phase_currents[2], 2),
                "cabinet_temperature_c": round(cabinet_temperature, 2),
                "surface_temperature_l1_c": round(surface_temperatures[0], 2),
                "surface_temperature_l2_c": round(surface_temperatures[1], 2),
                "surface_temperature_l3_c": round(surface_temperatures[2], 2),
                "relative_humidity_pct": round(relative_humidity, 2),
                "pd_index": round(pd_index, 2),
                "pd_pulse_count": pd_pulse_count,
                "arc_status": int(arc_active),
                "overload_flag": int(overload_active),
                "connection_fault_flag": int(connection_active),
                "insulation_risk_flag": int(insulation_active),
            }
        )

    return rows


def validate_rows(rows: list[dict[str, object]]) -> None:
    expected_runs = sum(SCENARIO_COUNTS.values())
    expected_rows = expected_runs * STEPS_PER_RUN

    if len(rows) != expected_rows:
        raise ValueError(f"Expected {expected_rows} rows, got {len(rows)}.")

    rows_per_run: Counter[str] = Counter(str(row["run_id"]) for row in rows)
    if len(rows_per_run) != expected_runs:
        raise ValueError(f"Expected {expected_runs} runs, got {len(rows_per_run)}.")
    if any(count != STEPS_PER_RUN for count in rows_per_run.values()):
        raise ValueError("Every run must contain exactly 288 time steps.")

    for flag in (
        "overload_flag",
        "connection_fault_flag",
        "insulation_risk_flag",
        "arc_status",
    ):
        if not any(int(row[flag]) == 1 for row in rows):
            raise ValueError(f"No positive examples were generated for {flag}.")

    # A run must never leak into more than one split.
    splits_by_run: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        splits_by_run[str(row["run_id"])].add(str(row["split"]))
    if any(len(splits) != 1 for splits in splits_by_run.values()):
        raise ValueError("A run_id appears in more than one split.")


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, object]], output_path: Path) -> None:
    run_scenarios: dict[str, str] = {}
    run_splits: dict[str, str] = {}
    for row in rows:
        run_id = str(row["run_id"])
        run_scenarios.setdefault(run_id, str(row["scenario_label"]))
        run_splits.setdefault(run_id, str(row["split"]))

    scenario_counts = Counter(run_scenarios.values())
    split_counts = Counter(run_splits.values())

    print(f"Created: {output_path}")
    print(f"Rows: {len(rows):,}")
    print(f"Runs: {len(run_scenarios)}")
    print(f"Scenario runs: {dict(sorted(scenario_counts.items()))}")
    print(f"Split runs: {dict(sorted(split_counts.items()))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Grid Up switchboard telemetry."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/synthetic_telemetry.csv"),
        help="CSV output path (default: data/synthetic_telemetry.csv)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"Random seed (default: {SEED})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    master_rng = random.Random(args.seed)
    specs = build_run_specs(master_rng)

    rows: list[dict[str, object]] = []
    for run_number, spec in enumerate(specs, start=1):
        run_rng = random.Random(master_rng.randrange(0, 2**63))
        rows.extend(generate_run(run_number, spec, run_rng))

    validate_rows(rows)
    write_csv(rows, args.output)
    print_summary(rows, args.output)


if __name__ == "__main__":
    main()
