import unittest

from src.notifications.alarm_manager import AlarmManager


class FakeNotificationSender:
    def __init__(self):
        self.sent_messages = []

    def send(self, recipient, message):
        self.sent_messages.append(
            {
                "recipient": recipient,
                "message": message,
            }
        )

        return True


class FakeClock:
    def __init__(self):
        self.current_time = 0

    def __call__(self):
        return self.current_time

    def advance(self, seconds):
        self.current_time += seconds


def create_snapshot(**overrides):
    snapshot = {
        "module_id": "PANEL-001",
        "overload_risk": 10,
        "connection_risk": 8,
        "insulation_risk": 5,
        "arc_status": 0,
        "general_status": 0,
    }

    snapshot.update(overrides)
    return snapshot


class AlarmManagerTests(unittest.TestCase):
    def setUp(self):
        self.sender = FakeNotificationSender()
        self.clock = FakeClock()

        self.manager = AlarmManager(
            sender=self.sender,
            recipient="FIELD_TEAM",
            cooldown_seconds=300,
            clock=self.clock,
        )

    def test_normal_status_does_not_send_notification(self):
        snapshot = create_snapshot(
            general_status=0,
        )

        notification_sent = self.manager.process(snapshot)

        self.assertFalse(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 0)

    def test_warning_status_does_not_send_notification(self):
        snapshot = create_snapshot(
            general_status=1,
            overload_risk=45,
        )

        notification_sent = self.manager.process(snapshot)

        self.assertFalse(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 0)

    def test_high_risk_status_sends_notification(self):
        snapshot = create_snapshot(
            general_status=2,
            connection_risk=85,
        )

        notification_sent = self.manager.process(snapshot)

        self.assertTrue(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 1)
        self.assertIn(
            "Connection",
            self.sender.sent_messages[0]["message"],
        )

    def test_arc_sends_critical_notification(self):
        snapshot = create_snapshot(
            arc_status=1,
            general_status=0,
        )

        notification_sent = self.manager.process(snapshot)

        self.assertTrue(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 1)
        self.assertIn(
            "Arc detected",
            self.sender.sent_messages[0]["message"],
        )

    def test_same_alarm_is_suppressed_during_cooldown(self):
        snapshot = create_snapshot(
            arc_status=1,
            general_status=3,
        )

        first_result = self.manager.process(snapshot)
        second_result = self.manager.process(snapshot)

        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertEqual(len(self.sender.sent_messages), 1)

    def test_same_alarm_is_sent_after_cooldown(self):
        snapshot = create_snapshot(
            arc_status=1,
            general_status=3,
        )

        self.manager.process(snapshot)

        self.clock.advance(300)

        notification_sent = self.manager.process(snapshot)

        self.assertTrue(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 2)

    def test_different_dominant_risk_sends_new_notification(self):
        overload_snapshot = create_snapshot(
            general_status=2,
            overload_risk=85,
            connection_risk=20,
        )

        connection_snapshot = create_snapshot(
            general_status=2,
            overload_risk=20,
            connection_risk=90,
        )

        self.manager.process(overload_snapshot)
        notification_sent = self.manager.process(
            connection_snapshot
        )

        self.assertTrue(notification_sent)
        self.assertEqual(len(self.sender.sent_messages), 2)
        self.assertIn(
            "Connection",
            self.sender.sent_messages[1]["message"],
        )

    def test_recovery_notification_is_sent_once(self):
        critical_snapshot = create_snapshot(
            arc_status=1,
            general_status=3,
        )

        normal_snapshot = create_snapshot(
            arc_status=0,
            general_status=0,
        )

        self.manager.process(critical_snapshot)

        first_recovery = self.manager.process(normal_snapshot)
        second_recovery = self.manager.process(normal_snapshot)

        self.assertTrue(first_recovery)
        self.assertFalse(second_recovery)
        self.assertEqual(len(self.sender.sent_messages), 2)
        self.assertIn(
            "[RECOVERY]",
            self.sender.sent_messages[1]["message"],
        )


if __name__ == "__main__":
    unittest.main()