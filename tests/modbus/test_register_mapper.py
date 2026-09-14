from src.modbus.register_mapper import encode_snapshot

import unittest



class RegisterMapperTests(unittest.TestCase):

    def test_normal_snapshot(self):
        snapshot = {
            "current_l1_a": 318.0,
            "cabinet_temperature_c": 29.1,
            "surface_temperature_c": 50.3,
            "relative_humidity_pct": 50.9,
            "overload_risk": 10,
            "connection_risk": 8,
            "insulation_risk": 5,
            "arc_status": 0,
            "general_status": 0,
        }

        result = encode_snapshot(snapshot)

        self.assertEqual(
            result,
            [3180, 291, 503, 509, 10, 8, 5, 0, 0],
        )

    def test_negative_temperature(self):
        snapshot = {
            "current_l1_a": 318.0,
            "cabinet_temperature_c": -10.0,
            "surface_temperature_c": 20.0,
            "relative_humidity_pct": 50.0,
            "overload_risk": 0,
            "connection_risk": 0,
            "insulation_risk": 0,
            "arc_status": 0,
            "general_status": 0,
        }

        result = encode_snapshot(snapshot)

        self.assertEqual(result[1], 65436)

    def test_invalid_risk_score(self):
        snapshot = {
            "current_l1_a": 318.0,
            "cabinet_temperature_c": 29.1,
            "surface_temperature_c": 50.3,
            "relative_humidity_pct": 50.9,
            "overload_risk": 120,
            "connection_risk": 8,
            "insulation_risk": 5,
            "arc_status": 0,
            "general_status": 0,
        }

        with self.assertRaises(ValueError):
            encode_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()