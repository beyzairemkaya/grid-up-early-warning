import unittest

from src.modbus.register_mapper import encode_snapshot


def create_valid_snapshot(**overrides):
    snapshot = {
        "current_l1_a": 318.0,
        "current_l2_a": 315.0,
        "current_l3_a": 322.0,

        "cabinet_temperature_c": 29.1,
        "surface_temperature_l1_c": 50.3,
        "surface_temperature_l2_c": 49.7,
        "surface_temperature_l3_c": 51.0,

        "relative_humidity_pct": 50.9,

        "pd_index": 5.2,
        "pd_pulse_count": 3,

        "overload_risk": 10,
        "connection_risk": 8,
        "insulation_risk": 5,

        "arc_status": 0,
        "general_status": 0,
    }

    snapshot.update(overrides)
    return snapshot


class RegisterMapperTests(unittest.TestCase):

    def test_normal_snapshot(self):
        snapshot = create_valid_snapshot()

        result = encode_snapshot(snapshot)

        self.assertEqual(
            result,
            [
                3180,
                3150,
                3220,
                291,
                503,
                497,
                510,
                509,
                52,
                3,
                10,
                8,
                5,
                0,
                0,
            ],
        )

    def test_negative_temperature(self):
        snapshot = create_valid_snapshot(
            cabinet_temperature_c=-10.0,
        )

        result = encode_snapshot(snapshot)

        self.assertEqual(result[3], 65436)

    def test_invalid_risk_score(self):
        snapshot = create_valid_snapshot(
            overload_risk=120,
        )

        with self.assertRaises(ValueError):
            encode_snapshot(snapshot)

    def test_invalid_humidity(self):
        snapshot = create_valid_snapshot(
            relative_humidity_pct=110,
        )

        with self.assertRaises(ValueError):
            encode_snapshot(snapshot)

    def test_invalid_arc_status(self):
        snapshot = create_valid_snapshot(
            arc_status=2,
        )

        with self.assertRaises(ValueError):
            encode_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()