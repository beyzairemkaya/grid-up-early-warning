"""Checks the real risk engine -> Modbus register -> notification contract."""

import tempfile
import unittest
from pathlib import Path

from anomali_motoru_v2 import AnomaliMotoru, Okuma, Sonuc
from risk_snapshot_adapter import make_snapshot, risk_scores
from run_risk_snapshot import write_snapshot
from src.modbus.register_mapper import encode_snapshot
from src.modbus.scada_client import decode_registers
from src.notifications.alarm_manager import AlarmManager


class Sender:
    def __init__(self):
        self.messages = []

    def send(self, recipient, message):
        self.messages.append(message)
        return True


class RiskIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.engine = AnomaliMotoru()
        self.reading = Okuma(
            i_r=318.0, i_s=315.0, i_t=322.0,
            sicaklik_r=50.3, sicaklik_s=49.7, sicaklik_t=51.0,
            nem_rh=50.9, pd_pc=5.2, ortam_c=29.1,
        )

    def snapshot(self, reading):
        result = self.engine.adim(reading)
        snapshot = make_snapshot(
            reading, result, cabinet_temperature_c=29.1,
            pd_pulse_count=3, pd_critical_pc=self.engine.e.PD_KRITIK_PC,
        )
        self.assertEqual(len(snapshot), 15)
        return decode_registers(encode_snapshot(snapshot))

    def test_normal_and_high_risk_notification_and_recovery(self):
        sender = Sender()
        manager = AlarmManager(sender, recipient="FIELD_TEAM", clock=lambda: 0)
        normal = self.snapshot(self.reading)
        self.assertEqual(normal["general_status"], 0)
        self.assertFalse(manager.process(normal))

        hot_l2 = Okuma(**{**vars(self.reading), "sicaklik_s": 80.0})
        high = self.snapshot(hot_l2)
        self.assertEqual(high["connection_risk"], 85)
        self.assertEqual(high["general_status"], 2)
        self.assertTrue(manager.process(high))
        self.assertIn("Connection (85/100)", sender.messages[-1])
        self.assertFalse(manager.process(high))  # cooldown

        self.assertTrue(manager.process(self.snapshot(self.reading)))
        self.assertIn("[RECOVERY]", sender.messages[-1])

    def test_pd_critical_and_arc_are_critical(self):
        pd = Okuma(**{**vars(self.reading), "pd_pc": 260.0})
        pd_snapshot = self.snapshot(pd)
        self.assertEqual(pd_snapshot["insulation_risk"], 90)
        self.assertEqual(pd_snapshot["general_status"], 3)

        arc = Okuma(**{**vars(self.reading), "ark_lux": 5500.0})
        arc_snapshot = self.snapshot(arc)
        self.assertEqual(arc_snapshot["arc_status"], 1)
        self.assertEqual(arc_snapshot["general_status"], 3)

    def test_overload_score_and_no_pulse_fabrication(self):
        result = Sonuc(zaman=None, bitmap=0, seviye="UYARI",
                       alarmlar=["FAZ_DENGESIZLIGI", "ASIRI_YUK"])
        self.assertEqual(risk_scores(result)["overload_risk"], 90)
        with self.assertRaises(ValueError):
            make_snapshot(self.reading, result, cabinet_temperature_c=29.1,
                          pd_pulse_count=-1)

    def test_atomic_snapshot_is_valid_json(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime" / "snapshot.json"
            write_snapshot(path, make_snapshot(
                self.reading, self.engine.adim(self.reading),
                cabinet_temperature_c=29.1, pd_pulse_count=3,
            ))
            self.assertEqual(json.loads(path.read_text())["general_status"], 0)


if __name__ == "__main__":
    unittest.main()
