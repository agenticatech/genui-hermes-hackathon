#!/bin/sh
# Install the demo sandboxes on the Hermes host (run there, from the directory holding these files):
# the pr stand-in, the release pipeline, and the setup scripts, under ~/genui-sandbox.
set -e
S="$HOME/genui-sandbox"
mkdir -p "$S/bin" "$S/release"
install -m 755 pr "$S/bin/pr"
install -m 755 release.sh "$S/release/release.sh"
install -m 755 setup_pr.sh setup_release.sh "$S/bin/"
echo "installed in $S: bin/pr, bin/setup_pr.sh, bin/setup_release.sh, release/release.sh"
