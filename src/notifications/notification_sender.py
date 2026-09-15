import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

class NotificationSender(ABC):
    @abstractmethod
    def send(self,recipient,message):
        """Send a notification and return whether it succeeded."""
        raise NotImplementedError


class ConsoleNotificationSender(NotificationSender):
    def send(self,recipient,message):
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print("\n--- Notification Simulation ---")
        print(f"Time: {timestamp}")
        print(f"Recipient: {recipient}")
        print(f"Message: {message}")
        print("Delivery status: Simulated successfully")

        return True

class LoggedNotificationSender(NotificationSender):
    def __init__(self, sender, log_file):
        self.sender = sender
        self.log_file = Path(log_file)

    def send(self, recipient, message):
        sent_successfully = self.sender.send(
            recipient,
            message,
        )

        record = {
            "timestamp": datetime.now().isoformat(
                timespec="seconds"
            ),
            "recipient": recipient,
            "message": message,
            "successful": sent_successfully,
        }

        try:
            self.log_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.log_file.open(
                "a",
                encoding="utf-8",
            ) as file:
                file.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        except OSError as error:
            print(
                f"Notification log could not be written: {error}"
            )

        return sent_successfully

