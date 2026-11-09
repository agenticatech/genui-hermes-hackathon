#!/usr/bin/env bash
# (Re)create the pull-request sandbox for the demo video: a real git repository at
# ~/genui-sandbox/webapp on branch feat/session-refresh (3 commits not pushed yet, 4 files of
# uncommitted work) and its origin, a bare repository where main moved on meanwhile: Lena rotated
# the session keys and changed the same lines in src/auth.ts and src/middleware.ts, so merging
# main into the branch conflicts in 3 places. ~/genui-sandbox/bin/pr stands in for `gh pr`.
# Run it before every take: it wipes the previous one.
set -euo pipefail
S="$HOME/genui-sandbox"
rm -rf "$S/webapp" "$S/remote" "$S/.lena"
mkdir -p "$S/remote" "$S/bin"
git init -q --bare -b main "$S/remote/webapp.git"

ago() { date -d "-$1" "+%Y-%m-%dT%H:%M:%S"; }
commit() {  # commit "<author>" "<email>" "<age>" "<message>"
  GIT_AUTHOR_NAME="$1" GIT_AUTHOR_EMAIL="$2" GIT_COMMITTER_NAME="$1" GIT_COMMITTER_EMAIL="$2" \
  GIT_AUTHOR_DATE="$(ago "$3")" GIT_COMMITTER_DATE="$(ago "$3")" git commit -q -m "$4"
}

git clone -q "$S/remote/webapp.git" "$S/webapp" 2>/dev/null
cd "$S/webapp"
git config user.name "You"
git config user.email "you@acme.dev"
mkdir -p src

# --- main, 3 hours ago -------------------------------------------------------------------------
cat > package.json <<'EOF'
{
  "name": "acme-webapp",
  "private": true,
  "scripts": { "dev": "next dev", "build": "next build" },
  "dependencies": { "next": "16.3.0" }
}
EOF
cat > src/keys.ts <<'EOF'
export const keys = {
  primary: process.env.SESSION_KEY!,
};
EOF
cat > src/auth.ts <<'EOF'
import { verify } from "./jwt";
import { keys } from "./keys";

export const MINUTE = 60_000;

export function readToken(header: string | undefined) {
  if (!header?.startsWith("Bearer ")) return null;
  return header.slice(7);
}

export function checkToken(token: string) {
  return verify(token, keys.primary);
}

export function sessionTtl(session: { expiresAt: number }) {
  const ttl = 30 * MINUTE;
  return Math.max(ttl, 0);
}
EOF
cat > src/middleware.ts <<'EOF'
import { readToken, checkToken } from "./auth";
import { readSession } from "./session";

export async function auth(req, res, next) {
  const token = readToken(req.headers.authorization);
  if (!token) return res.status(401).end();
  const session = await readSession(req);
  if (!session || !checkToken(token)) return res.status(401).end();
  req.session = session;
  next();
}
EOF
printf '# acme-webapp\n\nThe Acme web app.\n' > README.md
git add -A
commit "Sam" "sam@acme.dev" "3 hours" "Bump next to 16.3"
git push -q origin main

# --- feat/session-refresh, yours ---------------------------------------------------------------
git checkout -q -b feat/session-refresh
sed -i 's/  const ttl = 30 \* MINUTE;/  const ttl = session.expiresAt - Date.now();/' src/auth.ts
git add -A
commit "You" "you@acme.dev" "40 minutes" "Read session expiry from the token"

cat > src/refresh.ts <<'EOF'
import { MINUTE } from "./auth";

export function refreshIfNear<T extends { exp: number }>(claims: T, margin = 5 * MINUTE) {
  return claims.exp * 1000 - Date.now() < margin ? { ...claims, refresh: true } : claims;
}

export async function refreshIfNeeded(session) {
  return session && session.expiresAt - Date.now() < 5 * MINUTE ? session.refresh() : session;
}
EOF
sed -i 's/  return verify(token, keys.primary);/  return refreshIfNear(verify(token, keys.primary), 5 * MINUTE);/' src/auth.ts
sed -i 's/^import { keys } from ".\/keys";/import { keys } from ".\/keys";\nimport { refreshIfNear } from ".\/refresh";/' src/auth.ts
sed -i 's/  const session = await readSession(req);/  const session = await refreshIfNeeded(await readSession(req));/' src/middleware.ts
sed -i 's/^import { readSession } from ".\/session";/import { readSession } from ".\/session";\nimport { refreshIfNeeded } from ".\/refresh";/' src/middleware.ts
git add -A
commit "You" "you@acme.dev" "25 minutes" "Refresh sessions near expiry"

# Uncommitted work: the tests for it, 4 files.
cat > src/session.test.ts <<'EOF'
import { describe, it, expect } from "vitest";
import { refreshIfNear } from "./refresh";
import { session } from "./session.fixtures";

describe("refreshIfNear", () => {
  it("refreshes a token about to expire", () => {
    expect(refreshIfNear({ exp: Date.now() / 1000 + 60 }).refresh).toBe(true);
  });
  it("leaves a fresh token alone", () => {
    expect(refreshIfNear({ exp: Date.now() / 1000 + 3600 })).not.toHaveProperty("refresh");
  });
  it("keeps the session it was given", () => {
    expect(session.expiresAt).toBeGreaterThan(0);
  });
});
EOF
printf 'export const session = { id: "s_42", expiresAt: Date.now() + 10 * 60_000 };\n' > src/session.fixtures.ts
sed -i 's/"build": "next build" }/"build": "next build", "test": "vitest run" }/' package.json
printf '\n## Sessions\n\nSessions about to expire are refreshed by the auth middleware.\n' >> README.md

# --- meanwhile on origin/main: Lena -------------------------------------------------------------
git clone -q "$S/remote/webapp.git" "$S/.lena"
cd "$S/.lena"
git config user.name "Lena Park"
git config user.email "lena@acme.dev"
cat > src/keys.ts <<'EOF'
export const keys = {
  current: { secret: process.env.SESSION_KEY!, ttl: 30 * 60_000 },
  previous: { secret: process.env.SESSION_KEY_PREVIOUS ?? "", ttl: 30 * 60_000 },
};
EOF
sed -i 's/  return verify(token, keys.primary);/  return verify(token, keys.current);/' src/auth.ts
sed -i 's/  const ttl = 30 \* MINUTE;/  const ttl = keys.current.ttl;/' src/auth.ts
git add -A
commit "Lena Park" "lena@acme.dev" "18 minutes" "Rotate session keys"
sed -i 's/  const session = await readSession(req);/  const session = await readSession(req, keys);/' src/middleware.ts
sed -i 's/^import { readSession } from ".\/session";/import { readSession } from ".\/session";\nimport { keys } from ".\/keys";/' src/middleware.ts
git add -A
commit "Lena Park" "lena@acme.dev" "6 minutes" "Read sessions with the current key"
git push -q origin main
cd "$S"
rm -rf "$S/.lena"

cd "$S/webapp"
git fetch -q origin
echo "PR sandbox ready: $S/webapp on $(git rev-parse --abbrev-ref HEAD), $(git rev-list --count origin/main..HEAD) commits to push, $(git status --porcelain | wc -l) files uncommitted; origin/main is 2 commits ahead."
