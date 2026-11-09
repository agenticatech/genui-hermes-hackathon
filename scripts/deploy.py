"""Deploy the agent half of plugin/ to the Hermes host over SSH.

    python scripts/deploy.py                # copy files only (picked up on next restart)
    python scripts/deploy.py --restart      # copy, then restart the dashboard so routes/tools reload
    python scripts/deploy.py --enable       # first install: add genui to plugins.enabled

The desktop half (plugin/desktop/) is not sent: against a remote backend, Desktop loads plugins
from the PC, where %LOCALAPPDATA%\\hermes\\desktop-plugins\\genui links to plugin/desktop/.
"""
import argparse
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ROOT / "plugin"
PLUGIN_ID = "genui"
REMOTE_DIR = f"~/.hermes/plugins/{PLUGIN_ID}"
DASHBOARD_SERVICE = "hermes-dashboard"
EXCLUDED = {"desktop", "__pycache__", ".pytest_cache"}

load_dotenv(ROOT / ".env")


def pack() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in sorted(PLUGIN_DIR.rglob("*")):
            rel = path.relative_to(PLUGIN_DIR)
            if path.is_file() and not EXCLUDED & set(rel.parts) and path.suffix != ".pyc":
                tar.add(path, arcname=rel.as_posix())
    return buf.getvalue()


def ssh(host: str, command: str, stdin: bytes = b"") -> int:
    # Non-interactive SSH skips ~/.bashrc, where the Hermes installer adds ~/.local/bin to PATH.
    return subprocess.run(["ssh", "-o", "BatchMode=yes", host, f'export PATH="$HOME/.local/bin:$PATH"; {command}'],
                          input=stdin).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("HERMES_HOST"), help="SSH host (default: $HERMES_HOST)")
    ap.add_argument("--enable", action="store_true", help=f"run `hermes plugins enable {PLUGIN_ID}`")
    ap.add_argument("--restart", action="store_true", help=f"restart the {DASHBOARD_SERVICE} service")
    args = ap.parse_args()
    if not args.host:
        ap.error("--host (or HERMES_HOST in .env) is required")

    archive = pack()
    if ssh(args.host, f'rm -rf {REMOTE_DIR} && mkdir -p {REMOTE_DIR} && tar -xzf - -C {REMOTE_DIR} && ls {REMOTE_DIR}', archive):
        sys.exit("copy failed")
    print(f"deployed {len(archive)} bytes to {args.host}:{REMOTE_DIR}")
    if args.enable and ssh(args.host, f"hermes plugins enable {PLUGIN_ID}"):
        sys.exit("enable failed")
    if args.restart:
        if ssh(args.host, f"systemctl restart {DASHBOARD_SERVICE} && sleep 3 && systemctl is-active {DASHBOARD_SERVICE}"):
            sys.exit("restart failed")
        print(f"{DASHBOARD_SERVICE} restarted")


if __name__ == "__main__":
    main()
