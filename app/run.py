"""Start the API and the UI together (used by `make app`). Ctrl+C stops both."""

import subprocess
import sys
import time

COMMANDS = [
    [sys.executable, "-m", "uvicorn", "app.api:app", "--port", "8000"],
    [sys.executable, "-m", "streamlit", "run", "app/ui.py", "--server.port", "8501"],
]


def main() -> None:
    processes = [subprocess.Popen(command) for command in COMMANDS]
    print("API: http://localhost:8000/docs   UI: http://localhost:8501")
    try:
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            process.terminate()


if __name__ == "__main__":
    main()
