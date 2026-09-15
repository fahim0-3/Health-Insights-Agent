"""Start the local session service and Streamlit together for development."""

import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn

from session_server import app


def main():
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8503, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.5)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(__file__).with_name("main.py")),
                "--server.port",
                "8502",
            ],
            check=False,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
