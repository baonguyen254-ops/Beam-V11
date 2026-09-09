"""Run the bundled v11 UI and API together, with one persistent-state worker."""

import argparse
import os
import sys
import threading
import webbrowser
import secrets
from datetime import datetime
from pathlib import Path


def main():
    if sys.version_info < (3, 12):
        raise SystemExit("BEAM v11 requires Python 3.12 or later.")
    parser = argparse.ArgumentParser(
        description="BEAM v11.1 English Hospital Dashboard"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--open", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--demo",
        action="store_true",
        help="Open the isolated, fully populated synthetic demo",
    )
    mode.add_argument(
        "--standard", action="store_true", help="Use standard setup and BEAM_DATA_DIR"
    )
    parser.add_argument(
        "--new-demo",
        action="store_true",
        help="Create a separate fresh demo without deleting previous sessions",
    )
    parser.add_argument(
        "--demo-data-dir",
        help="Use a separate demo data directory; existing non-demo records are rejected",
    )
    args = parser.parse_args()
    backend = Path(__file__).resolve().parent / "beam-backend"
    demo = (
        args.demo
        or args.new_demo
        or bool(args.demo_data_dir)
        or (not args.standard and not os.environ.get("BEAM_DATA_DIR"))
    )
    if args.standard and (args.new_demo or args.demo_data_dir):
        parser.error("Demo options cannot be used with --standard")
    if args.new_demo and args.demo_data_dir:
        parser.error("Choose --new-demo or --demo-data-dir")
    if demo:
        if args.host not in {"127.0.0.1", "localhost", "::1"}:
            parser.error(
                "The demo presenter runs on loopback only. Use --standard for a network deployment."
            )
        demo_name = "demo-v11-1"
        if args.new_demo:
            demo_name += (
                "-"
                + datetime.now().strftime("%Y%m%d-%H%M%S")
                + "-"
                + secrets.token_hex(3)
            )
        os.environ["BEAM_DATA_DIR"] = str(
            Path(args.demo_data_dir).resolve()
            if args.demo_data_dir
            else backend / "data" / "runtime" / demo_name
        )
        os.environ["BEAM_DEMO"] = "1"
    else:
        os.environ["BEAM_DEMO"] = "0"
    if not (backend / "static/index.html").exists():
        raise SystemExit(
            "Frontend bundle missing. Run python tools/build_frontend.py with Node.js 22 installed."
        )
    sys.path.insert(0, str(backend))
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "Install dependencies first: python -m pip install -r beam-backend/requirements.txt"
        )
    print(
        f"BEAM v11.1: http://127.0.0.1:{args.port} | "
        + (
            "English demo: preparing synthetic records and history…"
            if demo
            else "Standard workspace; existing mode restored"
        ),
        flush=True,
    )
    print(
        "Data directory: "
        + os.environ.get("BEAM_DATA_DIR", str(backend / "data" / "runtime")),
        flush=True,
    )
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "Network binding enabled. Require HTTPS, approved origins and hospital network controls."
        )
    if args.open:
        threading.Timer(
            2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")
        ).start()
    uvicorn.run("main:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
