def scale_unsigned_by_ten(value):
    register_value = round(value * 10)

    if not 0 <= register_value <= 65535:
        raise ValueError(
            f"Value {value} cannot fit in an unsigned 16-bit register."
        )

    return register_value


def scale_signed_by_ten(value):
    scaled_value = round(value * 10)

    if not -32768 <= scaled_value <= 32767:
        raise ValueError(
            f"Value {value} cannot fit in a signed 16-bit register."
        )

    return scaled_value & 0xFFFF

def validate_score(score, name):
    score = round(score)

    if not 0 <= score <= 100:
        raise ValueError(f"{name} must be between 0 and 100.")

    return score

def encode_snapshot(snapshot):
    general_status = int(snapshot["general_status"])

    if general_status not in {0, 1, 2, 3}:
        raise ValueError("general_status must be 0, 1, 2, or 3.")

    arc_status = int(snapshot["arc_status"])

    if arc_status not in {0, 1}:
        raise ValueError("arc_status must be 0 or 1.")

    return [
    scale_unsigned_by_ten(snapshot["current_l1_a"]),
    scale_signed_by_ten(snapshot["cabinet_temperature_c"]),
    scale_signed_by_ten(snapshot["surface_temperature_c"]),
    scale_unsigned_by_ten(snapshot["relative_humidity_pct"]),
    validate_score(snapshot["overload_risk"], "overload_risk"),
    validate_score(snapshot["connection_risk"], "connection_risk"),
    validate_score(snapshot["insulation_risk"], "insulation_risk"),
    arc_status,
    general_status,
]