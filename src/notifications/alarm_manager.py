import time


STATUS_NAMES = {
    0: "NORMAL",
    1: "WARNING",
    2: "HIGH RISK",
    3: "CRITICAL",
}


RISK_NAMES = {
    "overload_risk": "Overload",
    "connection_risk": "Connection",
    "insulation_risk": "Insulation",
}


class AlarmManager:
    def __init__(
        self,
        sender,
        recipient,
        cooldown_seconds=300,
        clock=None,
    ):
        self.sender = sender
        self.recipient = recipient
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock or time.monotonic

        self.active_alarm_key = None
        self.last_sent_at = {}

    def process(self, snapshot):
        alarm = self._create_alarm(snapshot)

        if alarm is None:
            return self._handle_recovery(snapshot)

        alarm_key, message = alarm
        current_time = self.clock()
        last_sent_time = self.last_sent_at.get(alarm_key)

        alarm_changed = alarm_key != self.active_alarm_key
        cooldown_expired = (
            last_sent_time is None
            or current_time - last_sent_time >= self.cooldown_seconds
        )

        if not alarm_changed and not cooldown_expired:
            return False

        sent_successfully = self.sender.send(
            self.recipient,
            message,
        )

        if sent_successfully:
            self.active_alarm_key = alarm_key
            self.last_sent_at[alarm_key] = current_time
            return True

        return False

    def _create_alarm(self, snapshot):
        module_id = snapshot.get("module_id", "MODULE-001")

        arc_status = int(snapshot["arc_status"])
        general_status = int(snapshot["general_status"])

        if arc_status == 1:
            message = (
                f"[CRITICAL] Arc detected at {module_id}. "
                "Immediate field inspection is required."
            )

            return "ARC", message

        # Status 0 and 1 are displayed on the dashboard,
        # but do not trigger an urgent SMS.
        if general_status < 2:
            return None

        risk_scores = {
            risk_name: int(snapshot[risk_field])
            for risk_field, risk_name in RISK_NAMES.items()
        }

        dominant_risk = max(
            risk_scores,
            key=risk_scores.get,
        )
        dominant_score = risk_scores[dominant_risk]

        status_name = STATUS_NAMES.get(
            general_status,
            f"UNKNOWN STATUS {general_status}",
        )

        message = (
            f"[{status_name}] {module_id}: "
            f"Dominant risk is {dominant_risk} "
            f"({dominant_score}/100). "
            f"Overload={snapshot['overload_risk']}/100, "
            f"Connection={snapshot['connection_risk']}/100, "
            f"Insulation={snapshot['insulation_risk']}/100."
        )

        alarm_key = f"{general_status}:{dominant_risk}"

        return alarm_key, message

    def _handle_recovery(self, snapshot):
        if self.active_alarm_key is None:
            return False

        module_id = snapshot.get("module_id", "MODULE-001")

        message = (
            f"[RECOVERY] {module_id} returned below the "
            "high-risk notification level."
        )

        sent_successfully = self.sender.send(
            self.recipient,
            message,
        )

        if sent_successfully:
            self.active_alarm_key = None
            return True

        return False