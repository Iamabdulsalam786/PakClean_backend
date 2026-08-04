#!/usr/bin/env python3
"""
Save Gmail App Password into Pakclean_backend/.env and optionally send a test OTP email.

Usage:
  npm run gmail:setup              # interactive (terminal asks for password)
  npm run gmail:save -- xxxx       # paste 16-char App Password directly
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_TEST_EMAIL = "iamabdulsalam71@gmail.com"


def update_env_password(password: str) -> None:
    text = ENV_FILE.read_text(encoding="utf-8")
    cleaned = password.replace(" ", "").strip()

    if not re.fullmatch(r"[A-Za-z0-9]{16}", cleaned):
        print("❌ App Password must be 16 characters (spaces OK — we strip them).")
        sys.exit(1)

    if re.search(r"^SMTP_PASSWORD=.*$", text, flags=re.MULTILINE):
        text = re.sub(
            r"^SMTP_PASSWORD=.*$",
            f"SMTP_PASSWORD={cleaned}",
            text,
            flags=re.MULTILINE,
        )
    else:
        text = text.rstrip() + f"\nSMTP_PASSWORD={cleaned}\n"

    if re.search(r"^EMAIL_PROVIDER=.*$", text, flags=re.MULTILINE):
        text = re.sub(
            r"^EMAIL_PROVIDER=.*$",
            "EMAIL_PROVIDER=smtp",
            text,
            flags=re.MULTILINE,
        )
    else:
        text = text.rstrip() + "\nEMAIL_PROVIDER=smtp\n"

    if "SMTP_ENABLED=true" not in text:
        text = text.replace("SMTP_ENABLED=false", "SMTP_ENABLED=true")

    ENV_FILE.write_text(text, encoding="utf-8")
    print("✅ Saved SMTP_PASSWORD and EMAIL_PROVIDER=smtp to .env")


def send_test_email(to_email: str) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.integrations.email import deliver_otp_email, get_email_provider_status

    status = get_email_provider_status()
    print(f"   Email status: {status}")

    if not status.get("smtp_ready"):
        print("❌ SMTP still not ready — check .env (SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL)")
        sys.exit(1)

    result = deliver_otp_email(to_email=to_email, code="123456", expires_minutes=5)
    if not result.delivered:
        print(f"❌ Email failed: {result.detail}")
        sys.exit(1)

    print(f"✅ Test OTP email sent to {to_email} via {result.provider} — check inbox/spam")


def resolve_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password

    env_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if env_password:
        return env_password

    print("\n📧 Gmail App Password setup for PakClean OTP\n")
    print("1. Open: https://myaccount.google.com/apppasswords")
    print("2. Turn ON 2-Step Verification if not already enabled")
    print("3. Create App Password → App: Mail → Device: Other (PakClean)")
    print("4. Copy the 16-character password\n")
    print("Tip: npm run gmail:save -- YOUR_16_CHAR_PASSWORD\n")

    password = getpass.getpass("Paste Gmail App Password: ")
    if not password.strip():
        print("❌ No password entered.")
        sys.exit(1)
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Gmail SMTP for PakClean OTP emails")
    parser.add_argument(
        "--password",
        help="Gmail App Password (16 chars). Or use: npm run gmail:save -- xxxx",
    )
    parser.add_argument(
        "--test-email",
        default=DEFAULT_TEST_EMAIL,
        help=f"Send test OTP to this email (default: {DEFAULT_TEST_EMAIL})",
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Only save password to .env, do not send test email",
    )
    args = parser.parse_args()

    if not ENV_FILE.exists():
        print(f"❌ Missing {ENV_FILE}")
        sys.exit(1)

    password = resolve_password(args)
    update_env_password(password)

    if args.skip_test:
        print("✅ Done. Restart backend: npm run backend")
        return

    sys.path.insert(0, str(BACKEND_ROOT))
    try:
        send_test_email(args.test_email)
    except Exception as exc:
        print(f"❌ Email failed: {exc}")
        print("   Double-check App Password and that 2-Step Verification is ON.")
        sys.exit(1)


if __name__ == "__main__":
    main()
