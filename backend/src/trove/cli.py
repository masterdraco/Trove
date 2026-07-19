from __future__ import annotations

import argparse
import secrets
import sys

from sqlmodel import Session, select

from trove import __version__
from trove.db import get_engine, init_db
from trove.models.user import User
from trove.services import auth_service


def _reset_password(username: str, password: str | None) -> int:
    """Reset a user's password from the server (recovery when locked out)."""
    init_db()
    generated = password is None
    new_password = password or secrets.token_urlsafe(12)

    with Session(get_engine()) as session:
        user = auth_service.set_password_by_username(session, username, new_password)

    if user is None:
        existing = _usernames()
        print(f"No user named {username!r}.", file=sys.stderr)
        if existing:
            print(f"Known users: {', '.join(existing)}", file=sys.stderr)
        else:
            print("No users exist yet — finish setup in the web UI first.", file=sys.stderr)
        return 1

    print(f"Password updated for {username!r}.")
    if generated:
        print(f"New password: {new_password}")
        print("Log in with it, then change it under Settings → Account.")
    return 0


def _usernames() -> list[str]:
    with Session(get_engine()) as session:
        return [u.username for u in session.exec(select(User)).all()]


def _list_users() -> int:
    init_db()
    users = _usernames()
    if not users:
        print("No users exist yet.")
    else:
        for name in users:
            print(name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trove", description="Trove management CLI")
    parser.add_argument("--version", action="version", version=f"trove {__version__}")
    sub = parser.add_subparsers(dest="command")

    reset = sub.add_parser(
        "reset-password",
        help="Reset a user's password (recovery when locked out of the web UI)",
    )
    reset.add_argument("username", help="Username whose password to reset")
    reset.add_argument(
        "--password",
        help="New password. If omitted, a strong one is generated and printed.",
    )

    sub.add_parser("list-users", help="List existing usernames")

    args = parser.parse_args(argv)

    if args.command == "reset-password":
        if args.password is not None and len(args.password) < 8:
            parser.error("password must be at least 8 characters")
        return _reset_password(args.username, args.password)
    if args.command == "list-users":
        return _list_users()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
