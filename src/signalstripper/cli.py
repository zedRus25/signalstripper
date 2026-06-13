import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="signalstripper",
        description="Signal Backup Analysis & Reclaim Tool",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    analyze_p = sub.add_parser("analyze", help="Attribute storage by table/thread/type")
    analyze_p.add_argument("--db", type=Path, required=True, metavar="PATH")

    emit_p = sub.add_parser("emit", help="Generate reclaim command from a selection")
    emit_p.add_argument("--db", type=Path, required=True, metavar="PATH")
    emit_p.add_argument("--output", type=Path, default=None, metavar="PATH",
                        help="Write command to file instead of stdout")

    serve_p = sub.add_parser("serve", help="Launch the local selection UI")
    serve_p.add_argument("--db", type=Path, default=None, metavar="PATH")
    serve_p.add_argument("--mock", action="store_true", help="Use built-in mock data (no DB required)")
    serve_p.add_argument("--host", default="127.0.0.1", metavar="HOST")
    serve_p.add_argument("--port", type=int, default=8765, metavar="PORT")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "analyze":
        _cmd_analyze(args)
    elif args.command == "emit":
        _cmd_emit(args)
    elif args.command == "serve":
        _cmd_serve(args)


def _cmd_analyze(args: argparse.Namespace) -> None:
    import json
    from signalstripper.schema.registry import load_profiles
    from signalstripper.schema.introspect import introspect
    from signalstripper.analyze import analyze

    profiles = load_profiles()
    result = introspect(args.db, profiles)
    summary = analyze(args.db, result.profile)
    # Serialise dataclass tree to JSON
    import dataclasses
    print(json.dumps(dataclasses.asdict(summary), indent=2, default=str))


def _cmd_emit(args: argparse.Namespace) -> None:
    raise NotImplementedError("emit subcommand not yet implemented")


def _cmd_serve(args: argparse.Namespace) -> None:
    from signalstripper.server import create_app, serve

    if args.mock:
        from signalstripper.mock import mock_profile, mock_summary
        profile = mock_profile()
        summary = mock_summary()
        db_path = Path("/mock/signal.db")
    else:
        if not args.db:
            print("error: --db PATH is required unless --mock is set", file=sys.stderr)
            sys.exit(1)
        from signalstripper.schema.registry import load_profiles
        from signalstripper.schema.introspect import introspect
        from signalstripper.analyze import analyze
        profiles = load_profiles()
        result = introspect(args.db, profiles)
        summary = analyze(args.db, result.profile)
        profile = result.profile
        db_path = args.db

    app = create_app(db_path, profile, summary, mock=getattr(args, "mock", False))
    serve(app, host=args.host, port=args.port)
