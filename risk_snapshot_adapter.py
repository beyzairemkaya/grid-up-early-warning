"""Risk engine -> existing 15-register Modbus TCP snapshot (prototype only).

Place this file alongside ``anomali_motoru_v2.py``. Existing risk engine,
register mapper and Modbus server do not need to be changed.
"""

from __future__ import annotations

from anomali_motoru_v2 import Okuma, Sonuc


def risk_scores(result: Sonuc) -> dict[str, int]:
    """Transparent 0..100 rule scores, not calibrated failure probabilities."""
    alarms = set(result.alarmlar)

    imbalance = "FAZ_DENGESIZLIGI" in alarms
    overload = "ASIRI_YUK" in alarms
    overload_risk = 90 if imbalance and overload else 75 if overload else 40 if imbalance else 0

    contact = bool({"TERMAL_SAPMA", "KONTAK_SUPHESI_TABLO"} & alarms)
    connection_risk = 0
    if contact:
        connection_risk = 85 if "SICAKLIK_UYARI" in alarms else 70

    insulation_risk = 0
    if "NEM_YOGUSMA" in alarms:
        insulation_risk = 20
    if "PD_TREND_ARTISI" in alarms:
        insulation_risk = max(insulation_risk, 40)
    if "PD_UYARI" in alarms:
        insulation_risk = max(insulation_risk, 65)
    if "PD_KRITIK" in alarms:
        insulation_risk = 90

    return {
        "overload_risk": overload_risk,
        "connection_risk": connection_risk,
        "insulation_risk": insulation_risk,
    }


def general_status(result: Sonuc, scores: dict[str, int]) -> int:
    """0 normal, 1 warning, 2 high risk, 3 critical/arc."""
    if result.seviye in {"ACIL", "KRITIK"} or result.sistem_kilitli:
        return 3
    if max(scores.values()) >= 70:
        return 2
    if result.seviye in {"ON-UYARI", "UYARI"} or any(scores.values()):
        return 1
    if result.seviye != "NORMAL":
        raise ValueError(f"Unknown risk-engine level: {result.seviye!r}")
    return 0


def make_snapshot(
    reading: Okuma,
    result: Sonuc,
    *,
    cabinet_temperature_c: float,
    pd_pulse_count: int,
    pd_critical_pc: float = 250.0,
) -> dict:
    """Build the exact JSON object accepted by register_mapper.encode_snapshot.

    `cabinet_temperature_c` must come from a cabinet sensor (or explicitly
    designated simulated surrogate); it is not inferred from phase temperatures.
    `pd_pulse_count` must be measured or supplied by the test scenario.
    PD index is a *synthetic normalized proxy*, scaled 0..100 from charge in pC.
    """
    if not isinstance(pd_pulse_count, int) or not 0 <= pd_pulse_count <= 65535:
        raise ValueError("pd_pulse_count must be an integer from 0 to 65535")
    if pd_critical_pc <= 0:
        raise ValueError("pd_critical_pc must be positive")

    scores = risk_scores(result)
    arc = int(result.sistem_kilitli or bool({"ARK_FLASI", "SISTEM_KILITLI"} & set(result.alarmlar)))
    return {
        "current_l1_a": reading.i_r,
        "current_l2_a": reading.i_s,
        "current_l3_a": reading.i_t,
        "cabinet_temperature_c": cabinet_temperature_c,
        "surface_temperature_l1_c": reading.sicaklik_r,
        "surface_temperature_l2_c": reading.sicaklik_s,
        "surface_temperature_l3_c": reading.sicaklik_t,
        "relative_humidity_pct": reading.nem_rh,
        "pd_index": round(min(100.0, max(0.0, reading.pd_pc / pd_critical_pc * 100)), 1),
        "pd_pulse_count": pd_pulse_count,
        **scores,
        "arc_status": arc,
        "general_status": general_status(result, scores),
    }
