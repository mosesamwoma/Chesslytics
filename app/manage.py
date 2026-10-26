from __future__ import annotations

import argparse
import getpass
import sys

from app.database.database import init_db, session_scope
from app.services import digest_service, user_service


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


def send_digests(_args: argparse.Namespace) -> int:
    sent = digest_service.send_due()
    print(f"sent {sent} weekly digest(s)")
    return 0


def retag_command(_args: argparse.Namespace) -> int:
    from app.services import tactics_service

    init_db()
    tagged = tactics_service.retag_all()
    named = tactics_service.fill_openings_all()
    print(f"analysed the tactics of {tagged} mistake(s) and named {named} opening(s)")
    return 0


def import_puzzles_command(args: argparse.Namespace) -> int:
    from pathlib import Path

    from app.services import library_service

    init_db()
    path = Path(args.path)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    try:
        outcome = library_service.import_file(
            path,
            limit=args.limit,
            min_popularity=args.min_popularity,
            min_rating=args.min_rating,
            max_rating=args.max_rating,
            themes=args.theme,
            progress=lambda added, scanned: print(f"  added {added}, scanned {scanned}", flush=True),
        )
    except library_service.LibraryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"scanned {outcome['scanned']} rows, added {outcome['added']} puzzle(s), "
        f"skipped {outcome['skipped']} unusable row(s)"
    )
    return 0


def evaluate_tactics_command(args: argparse.Namespace) -> int:
    from pathlib import Path

    from app.chess import evaluation
    from app.services import library_service

    path = Path(args.path)
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    try:
        with library_service.open_text(path) as handle:
            report = evaluation.evaluate(library_service.parse_rows(handle), limit=args.limit)
    except library_service.LibraryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(evaluation.format_report(report))
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

    retag = sub.add_parser("retag", help="analyse tactics for older mistakes and name unnamed openings")
    retag.set_defaults(func=retag_command)

    puzzles = sub.add_parser("import-puzzles", help="import puzzles from the Lichess puzzle CSV (.csv or .csv.zst)")
    puzzles.add_argument("path")
    puzzles.add_argument("--limit", type=int, default=50000)
    puzzles.add_argument("--min-popularity", type=int, default=0)
    puzzles.add_argument("--min-rating", type=int, default=0)
    puzzles.add_argument("--max-rating", type=int, default=4000)
    puzzles.add_argument("--theme", action="append", help="only import puzzles with this Lichess theme (repeatable)")
    puzzles.set_defaults(func=import_puzzles_command)

    evaluate = sub.add_parser("evaluate-tactics", help="measure the tactic detectors against labelled Lichess puzzles")
    evaluate.add_argument("path")
    evaluate.add_argument("--limit", type=int, default=5000)
    evaluate.set_defaults(func=evaluate_tactics_command)

    digests = sub.add_parser("send-digests", help="send the weekly digest to everyone who is due")
    digests.set_defaults(func=send_digests)
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
