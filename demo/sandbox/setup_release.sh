#!/bin/sh
# Reset the release sandbox before a take: production back on 2.3.7.
#   setup_release.sh fail   the production deploy fails on a migration, the demo ends on a rollback
#   setup_release.sh ok     everything passes, the demo ends on 2.4.0 live
DIR="$HOME/genui-sandbox/release"
mkdir -p "$DIR"
echo "2.3.7" > "$DIR/.state"
case "${1:-fail}" in
  fail) touch "$DIR/.fail"; echo "release sandbox ready: production on 2.3.7, the 2.4.0 deploy will fail on migration 0042";;
  ok)   rm -f "$DIR/.fail"; echo "release sandbox ready: production on 2.3.7, the 2.4.0 deploy will pass";;
  *)    echo "usage: setup_release.sh fail|ok"; exit 2;;
esac
