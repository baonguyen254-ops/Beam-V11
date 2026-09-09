"""Build from the lockfile and copy static assets only after a successful build."""

import shutil
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit(
            "Node.js 22 and npm are required only when rebuilding frontend source."
        )
    frontend = root / "beam-frontend"
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    shutil.copytree(frontend / "dist", root / "beam-backend/static", dirs_exist_ok=True)
    for path in (root / "beam-backend/static/assets").glob("*"):
        if path.is_file() and not (frontend / "dist/assets" / path.name).exists():
            path.unlink()  # Only obsolete generated bundles, never source data.
    print("Frontend build copied to beam-backend/static. RUN_BEAM.py is ready.")


if __name__ == "__main__":
    main()
