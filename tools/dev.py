"""Start local API, durable worker and web server; stop all process groups on exit."""
import os
import shutil
import signal
import subprocess
import sys
import time
from _paths import ROOT


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm is required. Run the documented project setup first.")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "apps/api/src") + os.pathsep + env.get("PYTHONPATH", "")
    frontend_env = {key: value for key, value in env.items() if key not in {
        "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"}}
    commands = [
        [sys.executable, "-m", "uvicorn", "guide2build.main:app", "--host", "127.0.0.1", "--port", "8000"],
        [sys.executable, "tools/worker.py"],
        [npm, "run", "dev"],
    ]
    processes = []
    try:
        for command in commands:
            child_env = frontend_env if command[0] == npm else env
            processes.append(subprocess.Popen(command, cwd=ROOT, env=child_env, start_new_session=os.name != "nt"))
        print("API http://127.0.0.1:8000 | Web http://127.0.0.1:5173", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.4)
        return next((process.returncode for process in processes if process.returncode), 1)
    except KeyboardInterrupt:
        return 0
    finally:
        # uv/terminal may forward SIGINT twice; finish child cleanup once begun.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for process in processes:
            try:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGTERM)
                elif process.poll() is None:
                    process.terminate()
            except PermissionError:
                # Some managed shells permit signaling our child but deny group signals.
                if process.poll() is None:
                    process.terminate()
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()

if __name__ == "__main__":
    raise SystemExit(main())
