#!/usr/bin/env python3

import argparse
import os
import smtplib
import socket
import sys
from email.message import EmailMessage
from pathlib import Path


DEFAULT_ENV_FILE = "/etc/training/alert.env"


def load_env_file(path: str) -> dict[str, str]:
    env_path = Path(path)

    if not env_path.is_file():
        raise FileNotFoundError(f"Alert configuration not found: {env_path}")

    values: dict[str, str] = {}

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise ValueError(f"Invalid configuration line in {env_path}")

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    required = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_APP_PASSWORD",
        "ALERT_FROM",
        "ALERT_TO",
    ]

    missing = [key for key in required if not values.get(key)]

    if missing:
        raise ValueError(
            "Missing required alert configuration: " + ", ".join(missing)
        )

    return values


def send_alert(subject: str, body: str, env_file: str = DEFAULT_ENV_FILE) -> None:
    config = load_env_file(env_file)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["ALERT_FROM"]
    message["To"] = config["ALERT_TO"]
    message.set_content(body)

    smtp_host = config["SMTP_HOST"]
    smtp_port = int(config["SMTP_PORT"])

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(
            config["SMTP_USER"],
            config["SMTP_APP_PASSWORD"],
        )
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a HarrisServer alert through Gmail SMTP."
    )

    parser.add_argument(
        "--subject",
        required=True,
        help="Email subject",
    )

    parser.add_argument(
        "--body",
        required=True,
        help="Plain-text email body",
    )

    parser.add_argument(
        "--env-file",
        default=os.environ.get("ALERT_ENV_FILE", DEFAULT_ENV_FILE),
        help=f"Alert configuration file, default: {DEFAULT_ENV_FILE}",
    )

    arguments = parser.parse_args()

    try:
        send_alert(
            subject=arguments.subject,
            body=arguments.body,
            env_file=arguments.env_file,
        )
    except smtplib.SMTPAuthenticationError:
        print(
            "ERROR: Gmail rejected the SMTP credentials. "
            "Verify the Gmail address and App Password.",
            file=sys.stderr,
        )
        return 1
    except smtplib.SMTPException as error:
        print(
            f"ERROR: SMTP delivery failed: {type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    except (FileNotFoundError, PermissionError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (socket.timeout, TimeoutError, OSError) as error:
        print(
            f"ERROR: Network connection failed: {type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(
            f"ERROR: Unexpected alert failure: {type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    print("Alert email sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())