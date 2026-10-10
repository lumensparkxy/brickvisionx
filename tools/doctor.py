"""Non-invasive preflight. Never prints environment secrets or installs global software."""
import importlib.util
import shutil
import subprocess
import sys
import tomllib
from _paths import ROOT


def main() -> int:
    print(f"Project: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    for name in ("node", "npm", "uv", "codex", "git"):
        executable = shutil.which(name)
        if not executable:
            print(f"{name}: missing (Codex is an optional development tool)")
            continue
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15)
        print(f"{name}: {result.stdout.strip().splitlines()[0] if result.stdout.strip() else 'installed'}")
    for path in ("project.toml", "pyproject.toml", ".codex/config.toml"):
        with (ROOT / path).open("rb") as handle:
            tomllib.load(handle)
        print(f"TOML valid: {path}")
    for module in ("fastapi", "pydantic", "httpx", "pypdfium2", "pytest", "google.adk", "google.genai", "dotenv"):
        try:
            installed = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            installed = False
        print(f"Python module {module}: {'installed' if installed else 'missing'}")
    print("Runtime inference: Google ADK + Gemini Developer API; GOOGLE_API_KEY is backend-only.")
    print("Defaults: gemini-3.8-flash, medium thinking, 120 seconds, three requests per job.")
    print("No external network check, package installation, credential access or paid call was performed.")
    print("Read docs/14_SCAFFOLD_STATUS.md: this preflight is not an application acceptance test.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
