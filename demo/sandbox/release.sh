#!/bin/sh
# Release pipeline stand-in for the demo video: release.sh build|staging|smoke|prod|health|rollback VERSION
# Production runs 2.3.7. With setup_release.sh fail, the production deploy fails on its second
# migration (a lock timeout) and leaves the first one applied, so the only safe move is rollback.
DIR="$(dirname "$0")"
STATE="$DIR/.state"
[ -f "$STATE" ] || echo "2.3.7" > "$STATE"
case "$1" in
  build)   sleep 4; echo "built ghcr.io/acme/webapp:$2 in 94 s (1284 modules)";;
  staging) sleep 3; echo "deployed $2 to https://staging.acme.dev in 41 s (3/3 pods ready)";;
  smoke)   sleep 5; echo "smoke tests on staging: 18 passed, 0 failed (playwright, 52 s)";;
  prod)
    sleep 3
    echo "migrate: 0041_rotate_keys ... ok"
    if [ -f "$DIR/.fail" ]; then
      sleep 2
      echo "migrate: 0042_add_session_index ... ERROR: canceling statement due to lock timeout"
      echo "  relation \"sessions\" is locked by pid 3317 (long-running analytics export)"
      echo "deploy aborted: production still serves $(cat "$STATE"); 0041_rotate_keys stays applied"
      exit 1
    fi
    sleep 1
    echo "migrate: 0042_add_session_index ... ok"
    echo "deployed $2 to production in 38 s (8/8 pods ready)"
    echo "$2" > "$STATE"
    ;;
  health)  sleep 2; echo "healthy: $(cat "$STATE") serving, error rate 0.1%, p95 180 ms";;
  rollback)
    sleep 3
    echo "revert: 0041_rotate_keys ... ok"
    echo "rolled back: production serves $(cat "$STATE"), migrations back at 0040"
    ;;
  *) echo "usage: release.sh build|staging|smoke|prod|health|rollback VERSION"; exit 2;;
esac
