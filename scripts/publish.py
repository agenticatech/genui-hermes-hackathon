"""Publish a release of this repository to its public GitHub repository, as one commit.

The public repository gets the exact tree of a local commit (default: HEAD), authored by the public
account, on top of what it already has; this repository's own history stays private. Prints the
40-character sha to pin in the plugin catalog.

    python scripts/publish.py --remote https://<user>@github.com/<user>/hermes-genui.git \
        --name "<user>" --email "<id>+<user>@users.noreply.github.com" -m "GenUI 0.2.0"

The user name in the remote URL makes Git Credential Manager ask for (and keep) that account's
login, separately from the one this repository's origin uses.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def git(*args: str, env: dict | None = None, check: bool = True) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
    if check and done.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{done.stderr.strip()}")
    return done.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remote", required=True, help="the public repository's https URL")
    ap.add_argument("--name", required=True, help="the public account's name, as the commit author")
    ap.add_argument("--email", required=True, help="its email, ideally the GitHub noreply address")
    ap.add_argument("-m", "--message", required=True)
    ap.add_argument("--ref", default="HEAD", help="the local commit whose tree is published (default HEAD)")
    ap.add_argument("--branch", default="main")
    a = ap.parse_args()

    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("uncommitted changes: commit them first, the published tree is the one of --ref")
    tree = git("rev-parse", f"{a.ref}^{{tree}}")
    head = git("ls-remote", a.remote, f"refs/heads/{a.branch}").split()
    parents = []
    if head:
        git("fetch", "--quiet", a.remote, f"refs/heads/{a.branch}")
        parents = ["-p", git("rev-parse", "FETCH_HEAD")]
        if git("rev-parse", "FETCH_HEAD^{tree}") == tree:
            print(f"{a.branch} already has this tree: {parents[1]}")
            return
    env = {**os.environ, "GIT_AUTHOR_NAME": a.name, "GIT_AUTHOR_EMAIL": a.email,
           "GIT_COMMITTER_NAME": a.name, "GIT_COMMITTER_EMAIL": a.email}
    sha = git("commit-tree", tree, *parents, "-m", a.message, env=env)
    git("push", a.remote, f"{sha}:refs/heads/{a.branch}")
    print(f"published {sha} to {a.remote} ({a.branch})")
    print(f"pin it in plugin-catalog/genui.yaml: sha: {sha}")


if __name__ == "__main__":
    main()
