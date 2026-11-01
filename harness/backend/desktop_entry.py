"""Loopback-only entry point for the standalone desktop backend."""
import argparse
import os
import sys
from pathlib import Path


def port_number(value):
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("Port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description="Luminfest desktop backend (loopback only)")
    parser.add_argument("--port", type=port_number, default=os.getenv("HARNESS_PORT", "8765"))
    parser.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1",
                        help="Only loopback hosts are accepted; binding always uses 127.0.0.1")
    args = parser.parse_args(argv)
    os.environ.setdefault("HARNESS_DATA_DIR", str(
        Path.home() / "Library" / "Application Support" / "Luminfest Learning Harness"))
    os.environ.setdefault("HARNESS_AUTO_CREATE", "1")
    os.environ.setdefault("HARNESS_ADAPTATION", "0")
    os.environ.setdefault("HARNESS_ALLOWED_HOSTS", "localhost,127.0.0.1")

    import uvicorn
    from app.main import create_app
    if getattr(sys, "frozen", False):
        sys.dont_write_bytecode = True
        from app import adaptation
        adaptation.MODEL_DIR = Path(sys._MEIPASS) / "model"
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port, loop="asyncio", http="h11",
                ws="none", workers=1, reload=False, proxy_headers=False)


if __name__ == "__main__":
    main()
