def scale_unsigned_by_ten(value):
    register_value = round(value * 10)

    if not 0 <= register_value <= 65535:
        raise ValueError(
            f"Scaled value {register_value} cannot fit in an unsigned "
            "16-bit Modbus register."
        )

    return register_value


def scale_signed_by_ten(value):
    scaled_value = round(value * 10)

    if not -32768 <= scaled_value <= 32767:
        raise ValueError(
            f"Scaled value {scaled_value} cannot fit in a signed "
            "16-bit Modbus register."
        )

    return scaled_value & 0xFFFF


def validate_score(score, name):
    score = round(score)

    if not 0 <= score <= 100:
        raise ValueError(f"{name} must be between 0 and 100.")

    return score


def validate_percentage(value, name):
    value = float(value)

    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100.")

    return scale_unsigned_by_ten(value)


def validate_unsigned_integer(value, name):
    value = round(value)

    if not 0 <= value <= 65535:
        raise ValueError(
            f"{name} must be between 0 and 65535."
        )

    return value


def encode_snapshot(snapshot):
    general_status = int(snapshot["general_status"])

    if general_status not in {0, 1, 2, 3}:
        raise ValueError(
            "general_status must be 0, 1, 2, or 3."
        )

    arc_status = int(snapshot["arc_status"])

    if arc_status not in {0, 1}:
        raise ValueError("arc_status must be 0 or 1.")

    return [
        # 40001–40003: Phase currents
        scale_unsigned_by_ten(snapshot["current_l1_a"]),
        scale_unsigned_by_ten(snapshot["current_l2_a"]),
        scale_unsigned_by_ten(snapshot["current_l3_a"]),

        # 40004–40007: Cabinet and surface temperatures
        scale_signed_by_ten(snapshot["cabinet_temperature_c"]),
        scale_signed_by_ten(snapshot["surface_temperature_l1_c"]),
        scale_signed_by_ten(snapshot["surface_temperature_l2_c"]),
        scale_signed_by_ten(snapshot["surface_temperature_l3_c"]),

        # 40008: Relative humidity
        validate_percentage(
            snapshot["relative_humidity_pct"],
            "relative_humidity_pct",
        ),

        # 40009–40010: Processed PD indicators
        validate_percentage(
            snapshot["pd_index"],
            "pd_index",
        ),
        validate_unsigned_integer(
            snapshot["pd_pulse_count"],
            "pd_pulse_count",
        ),

        # 40011–40013: Explainable risk scores
        validate_score(
            snapshot["overload_risk"],
            "overload_risk",
        ),
        validate_score(
            snapshot["connection_risk"],
            "connection_risk",
        ),
        validate_score(
            snapshot["insulation_risk"],
            "insulation_risk",
        ),

        # 40014–40015: Event and system state
        arc_status,
        general_status,
    ]