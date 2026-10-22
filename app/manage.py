from __future__ import annotations

import argparse
import getpass
import sys

from app.database.database import init_db, session_scope
from app.services import user_service


def read_password(provided: str | None) -> str:
    if provided:
        return provided
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise SystemExit("error: passwords do not match")
    return first


def create_user(args: argparse.Namespace) -> int:
    password = read_password(args.password)
    role = user_service.ROLE_ADMIN if args.admin else user_service.ROLE_USER
    with session_scope() as session:
        user = user_service.create_user(
            session, args.username, password, role, allow_reserved=True
        )
        user_service.audit(session, "cli.create_user", target=user.username)
        print(f"created {role} {user.username} (id {user.id})")
    return 0


def reset_password(args: argparse.Namespace) -> int:
    password = read_password(args.password)
    with session_scope() as session:
        user = user_service.get_by_username(session, args.username)
        if user is None:
            print(f"error: no account named {args.username!r}", file=sys.stderr)
            return 2
        user_service.change_password(session, user, password)
        user.failed_logins = 0
        user.locked_until = None
        user_service.audit(session, "cli.reset_password", target=user.username)
        print(f"password reset for {user.username}; existing sessions were ended")
    return 0


def set_role(args: argparse.Namespace) -> int:
    with session_scope() as session:
        user = user_service.get_by_username(session, args.username)
        if user is None:
            print(f"error: no account named {args.username!r}", file=sys.stderr)
            return 2
        new_role = user_service.ROLE_ADMIN if args.admin else user_service.ROLE_USER
        if (
            new_role != user_service.ROLE_ADMIN
            and user.role == user_service.ROLE_ADMIN
            and user.is_active
            and user_service.count_active_admins(session) <= 1
        ):
            print("error: at least one administrator is required", file=sys.stderr)
            return 2
        user.role = new_role
        user.is_active = True
        user_service.revoke_sessions(session, user)
        user_service.audit(session, "cli.set_role", target=user.username, detail=user.role)
        print(f"{user.username} is now {user.role}")
    return 0


def list_users(_args: argparse.Namespace) -> int:
    with session_scope() as session:
        rows, total = user_service.list_users(session, None, 500, 0)
        for row in rows:
            state = "active" if row["is_active"] else "disabled"
            print(
                f"{row['id']:>5}  {row['username']:<32} {row['role']:<6} {state:<8} "
                f"games={row['games']} mistakes={row['mistakes']}"
            )
        print(f"{total} account(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="create an account")
    create.add_argument("username")
    create.add_argument("--admin", action="store_true")
    create.add_argument("--password", default=None)
    create.set_defaults(func=create_user)

    reset = sub.add_parser("reset-password", help="set a new password for an account")
    reset.add_argument("username")
    reset.add_argument("--password", default=None)
    reset.set_defaults(func=reset_password)

    role = sub.add_parser("set-role", help="make an account an administrator or a normal user")
    role.add_argument("username")
    role.add_argument("--admin", action="store_true")
    role.set_defaults(func=set_role)

    listing = sub.add_parser("list-users", help="list accounts")
    listing.set_defaults(func=list_users)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    init_db()
    try:
        return args.func(args)
    except user_service.UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
