import argparse
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from src.modbus.scada_client import read_snapshot
from src.notifications.alarm_manager import AlarmManager
from src.notifications.notification_sender import (
    ConsoleNotificationSender,
    LoggedNotificationSender,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Grid Up central Modbus alarm notification service"
        )
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Modbus TCP server address",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5020,
        help="Modbus TCP server port",
    )

    parser.add_argument(
        "--module-id",
        default="PANEL-001",
        help="Monitored field module identifier",
    )

    parser.add_argument(
        "--recipient",
        default="FIELD_TEAM",
        help="Notification recipient",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Modbus polling interval in seconds",
    )

    parser.add_argument(
        "--cooldown",
        type=float,
        default=300.0,
        help="Repeated alarm cooldown in seconds",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("runtime/alerts.jsonl"),
        help="Notification audit log file",
        )

    return parser.parse_args()


def main():
    args = parse_args()

    sender = LoggedNotificationSender(
    sender=ConsoleNotificationSender(),
    log_file=args.log_file,
)

    alarm_manager = AlarmManager(
        sender=sender,
        recipient=args.recipient,
        cooldown_seconds=args.cooldown,
    )

    client = ModbusTcpClient(
        host=args.host,
        port=args.port,
        timeout=3,
    )

    if not client.connect():
        print(
            f"Could not connect to Modbus server at "
            f"{args.host}:{args.port}."
        )
        raise SystemExit(1)

    print(
        f"Notification service connected to "
        f"{args.host}:{args.port}."
    )
    print(f"Monitoring module: {args.module_id}")
    print(f"Notification recipient: {args.recipient}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            try:
                snapshot = read_snapshot(client)
                snapshot["module_id"] = args.module_id

                notification_sent = alarm_manager.process(
                    snapshot
                )

                timestamp = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                status = snapshot["general_status"]
                arc_status = snapshot["arc_status"]

                if notification_sent:
                    result_text = "notification sent"
                else:
                    result_text = "no new notification"

                print(
                    f"[{timestamp}] "
                    f"module={args.module_id}, "
                    f"status={status}, "
                    f"arc={arc_status}, "
                    f"result={result_text}"
                )

            except (
                RuntimeError,
                ValueError,
                ModbusException,
            ) as error:
                print(f"Monitoring error: {error}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nNotification service stopped.")

    finally:
        client.close()


if __name__ == "__main__":
    main()