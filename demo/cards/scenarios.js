// One scripted task per use case: what the agent would send, step by step (show, then merge
// patches), with the waits between tool results and the clicks it waits for. The data follows the
// benchmark's scripted worlds and reference agents (benchmark/genui3), so the cards replay what a
// real run shows. A patch may be a function of ctx.values, what the user chose in the card.

const gb = (mb) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`)

// --- Pull request -------------------------------------------------------------------------------
const BASE = [
  { sha: 'c70a92', message: 'Refresh sessions near expiry', author: 'You', age: '25m', branch: 'feat/session-refresh' },
  { sha: 'e83c51', message: 'Add analytics consent banner', author: 'Sam', age: '32m', branch: 'feat/checkout-analytics' },
  { sha: '1f8e3b', message: 'Read session expiry from the token', author: 'You', age: '40m', branch: 'feat/session-refresh' },
  { sha: '62b0e4', message: 'Track checkout funnel events', author: 'Sam', age: '2h', branch: 'feat/checkout-analytics' },
  { sha: '9c2d4a', message: 'Bump next to 16.3', author: 'Sam', age: '3h', branch: 'main' },
]
const MINE = { sha: 'd29f50', message: 'Add session refresh tests', author: 'You', age: 'now', branch: 'feat/session-refresh' }
const lena = (state) => [
  { sha: '5be27d', message: 'Read sessions with the current key', author: 'Lena', age: '6m', branch: 'main', state: state[0] },
  { sha: 'a3f9c1', message: 'Rotate session keys', author: 'Lena', age: '18m', branch: 'main', state: state[1] },
]
const MERGE = (sha) => ({ sha, message: 'Merge main into feat/session-refresh', author: 'You', age: 'now', branch: 'feat/session-refresh', ...(sha === '-' ? { state: 'pending' } : {}) })
const HUNKS = [
  { file: 'middleware.ts', line: 18, by: 'Lena Park', theirs: 'const session = await readSession(req, keys)', ours: 'if (nearExpiry(session)) await refresh(session)' },
  { file: 'auth.ts', line: 42, by: 'Lena Park', theirs: 'return verify(token, keys.current)', ours: 'return refreshIfNear(token, 5 * MINUTE)' },
  { file: 'auth.ts', line: 57, by: 'Lena Park', theirs: 'const ttl = keys.current.ttl', ours: 'const ttl = session.expiresAt - Date.now()' },
]
const check = (name, state, detail, extra = {}) => ({ name, state, ...(detail ? { detail } : {}), ...extra })
const TESTS = (n) => n < 42 ? check('Tests', 'running', `${n}/42`, { done: n, total: 42 })
  : check('Tests', 'passed', '42 passed', { info: 'vitest · 42 passed, 0 failed', duration: '38s' })
const LINT = (s) => s ? check('Lint', 'passed', 'passed', { info: 'eslint · 0 problems', duration: '9s' }) : check('Lint', 'running')
const TYPES = (s) => s ? check('Types', 'passed', 'passed', { info: 'tsc --noEmit · no errors', duration: '21s' }) : check('Types', 'pending')
const PREVIEW = (s) => s === 2 ? check('Preview', 'passed', 'ready', { info: 'Deployed to session-refresh.preview.acme.dev', duration: '1m 4s' })
  : check('Preview', s ? 'running' : 'pending')

const PR = {
  label: 'Pull request · conflicts, then merge', type: 'pr_card', ask: 'Create PR',
  steps: [
    { wait: 700, show: { title: 'Refresh sessions in the auth middleware', status: 'committing', status_text: 'Committing the last changes',
      commits: [{ sha: '-', message: 'Uncommitted changes', author: 'You', age: '4 files', branch: 'feat/session-refresh', state: 'pending' }, ...BASE] } },
    { wait: 1700, patch: { status: 'pushing', status_text: 'Pushing 3 commits to origin', commits: [MINE, ...BASE] } },
    { wait: 1300, patch: { status: 'opening_pr', status_text: 'Opening the pull request' } },
    { wait: 1300, patch: { pr: 128, status: 'fetching', status_text: 'Fetching main' } },
    { wait: 1200, patch: { status: 'checking_merge', status_text: 'Checking it merges cleanly', commits: [MINE, ...lena(['new', 'new']), ...BASE] } },
    { wait: 1800, patch: { status: 'conflicts', status_text: '3 conflicts with main', commits: [MINE, ...lena(['conflict', 'conflict']), ...BASE],
      conflicts: { total: 3, resolved: 0, files: ['middleware.ts', 'auth.ts'], hunks: HUNKS },
      actions: [{ id: 'resolve_conflicts', label: 'Resolve conflicts', busy_label: 'Resolving' }] },
      say: 'PR #128 is open, but `main` moved on while we worked: Lena’s session key rotation changed the same lines in `auth.ts` and `middleware.ts`. I can merge `main` in and resolve them.' },
    { await: 'resolve_conflicts' },
    { wait: 450, patch: { status: 'resolving', status_text: 'Merging main into the branch', actions: [], commits: [MERGE('-'), MINE, ...lena(['conflict', 'conflict']), ...BASE] } },
    { wait: 1400, patch: { status_text: 'Resolving conflict 2 of 3', conflicts: { resolved: 1 } } },
    { wait: 1300, patch: { status_text: 'Resolving conflict 3 of 3', conflicts: { resolved: 2 }, commits: [MERGE('-'), MINE, ...lena(['resolved', 'conflict']), ...BASE] } },
    { wait: 1300, patch: { status: 'pushing_merge', status_text: 'Pushing the merge', conflicts: { resolved: 3 }, commits: [MERGE('7e0c3b'), MINE, ...lena(['resolved', 'resolved']), ...BASE] } },
    { wait: 1100, patch: { status: 'checks_running', status_text: 'Running 0 of 42 tests', checks: [TESTS(0), LINT(0), TYPES(0), PREVIEW(0)] } },
    { wait: 600, patch: { status_text: 'Running 9 of 42 tests', checks: [TESTS(9), LINT(1), TYPES(0), PREVIEW(1)] } },
    { wait: 600, patch: { status_text: 'Running 18 of 42 tests', checks: [TESTS(18), LINT(1), TYPES(0), PREVIEW(1)] } },
    { wait: 600, patch: { status_text: 'Running 25 of 42 tests', checks: [TESTS(25), LINT(1), TYPES(1), PREVIEW(1)] } },
    { wait: 600, patch: { status_text: 'Running 34 of 42 tests', checks: [TESTS(34), LINT(1), TYPES(1), PREVIEW(1)] } },
    { wait: 600, patch: { status_text: 'Running 42 of 42 tests', checks: [TESTS(41), LINT(1), TYPES(1), PREVIEW(2)] } },
    { wait: 700, patch: { status: 'ready', status_text: 'Ready to merge', checks: [TESTS(42), LINT(1), TYPES(1), PREVIEW(2)],
      actions: [{ id: 'merge', label: 'Merge', busy_label: 'Merging' }] } },
    { await: 'merge' },
    { wait: 400, patch: { status: 'merging', status_text: 'Merging into main', actions: [] } },
    { wait: 1500, patch: { status: 'merged', status_text: 'Merged into main', links: [{ label: 'GitHub', url: 'https://github.com/acme/webapp/pull/128' }] } },
  ],
}

// --- Release ------------------------------------------------------------------------------------
const plan = (states, details = {}) => [
  ['build', 'Build 2.4.0'], ['staging', 'Deploy to staging'], ['smoke', 'Smoke tests on staging'],
  ['prod', 'Deploy to production'], ['health', 'Production health check'],
].map(([id, label], i) => ({ id, label, state: states[i] || 'pending', ...(details[id] ? { detail: details[id] } : {}) }))
const DONE3 = { build: '94 s', staging: '41 s', smoke: '18 passed' }

const releaseStart = [
  { wait: 700, show: { title: 'Release 2.4.0', subtitle: 'acme-webapp · production runs 2.3.7', status: 'running', status_text: 'Building 2.4.0',
    steps: plan(['running']), log: ['vite v5.4.2 building for production…', 'transforming 1284 modules'] } },
  { wait: 1800, patch: { status_text: 'Deploying to staging', steps: plan(['done', 'running'], { build: '94 s' }),
    progress: { done: 1, total: 3, label: 'pods' }, log: ['pushed acme-webapp:2.4.0', 'rolling out to staging'] } },
  { wait: 700, patch: { progress: { done: 2, total: 3, label: 'pods' } } },
  { wait: 700, patch: { progress: { done: 3, total: 3, label: 'pods' } } },
  { wait: 800, patch: { status_text: 'Running smoke tests on staging', steps: plan(['done', 'done', 'running'], { build: '94 s', staging: '41 s' }),
    progress: { done: 4, total: 18 }, log: ['playwright test --project=smoke', '4 passed'] } },
  { wait: 600, patch: { progress: { done: 11, total: 18 } } },
  { wait: 600, patch: { progress: { done: 18, total: 18 } } },
  { wait: 700, patch: { status: 'waiting', status_text: 'Waiting for your go', steps: plan(['done', 'done', 'done'], DONE3), progress: null, log: null,
    explanation: 'Staging is green: 18 smoke tests passed on 2.4.0. Deploying runs the database migrations and users get the new version at once.',
    actions: [{ id: 'deploy_production', label: 'Deploy 2.4.0 to production', kind: 'primary', busy_label: 'Deploying' }] } },
  { await: 'deploy_production' },
  { wait: 450, patch: { status: 'running', status_text: 'Deploying 2.4.0 to production', steps: plan(['done', 'done', 'done', 'running'], DONE3),
    explanation: null, actions: [], progress: { done: 0, total: 2, label: 'migrations' }, log: ['migrate: 0041_rotate_keys'] } },
]

const RELEASE = {
  label: 'Release · ship 2.4.0', type: 'task_card', ask: 'Ship release 2.4.0 to production.',
  steps: [
    ...releaseStart,
    { wait: 1100, patch: { progress: { done: 1, total: 2, label: 'migrations' }, log: ['migrate: 0041_rotate_keys ✓', 'migrate: 0042_add_session_index'] } },
    { wait: 1100, patch: { progress: { done: 2, total: 2, label: 'migrations' } } },
    { wait: 800, patch: { status_text: 'Checking production health', progress: null, log: null,
      steps: plan(['done', 'done', 'done', 'done', 'running'], { ...DONE3, prod: '2 migrations' }) } },
    { wait: 1600, patch: { status: 'done', status_text: '2.4.0 is live', steps: plan(['done', 'done', 'done', 'done', 'done'], { ...DONE3, prod: '2 migrations', health: 'p95 180 ms' }),
      metrics: [{ label: 'error rate', value: '0.1%', tone: 'good' }, { label: 'p95 latency', value: '180 ms', tone: 'good' }] } },
  ],
}

const RELEASE_FAIL = {
  label: 'Release · migration fails, roll back', type: 'task_card', ask: 'Ship release 2.4.0 to production.',
  steps: [
    ...releaseStart,
    { wait: 1100, patch: { progress: { done: 1, total: 2, label: 'migrations' }, log: ['migrate: 0041_rotate_keys ✓', 'migrate: 0042_add_session_index'] } },
    { wait: 1500, patch: { status: 'failed', status_text: 'Production deploy failed', progress: null,
      steps: plan(['done', 'done', 'done', 'failed'], { ...DONE3, prod: 'lock timeout on table sessions' }),
      log: ['migrate: 0041_rotate_keys ✓', 'migrate: 0042_add_session_index', 'ERROR: canceling statement due to lock timeout', 'relation "sessions" is locked by pid 3317'],
      explanation: 'Migration 0042_add_session_index failed: lock timeout on table sessions. 0041_rotate_keys is applied while production still serves 2.3.7: roll back to undo it.',
      actions: [{ id: 'rollback_production', label: 'Roll back to 2.3.7', kind: 'danger', busy_label: 'Rolling back' }] } },
    { await: 'rollback_production' },
    { wait: 450, patch: { status: 'running', status_text: 'Rolling back production', explanation: null, actions: [], log: ['revert: 0041_rotate_keys'],
      steps: [...plan(['done', 'done', 'done', 'failed'], { ...DONE3, prod: 'lock timeout on table sessions' }), { id: 'rollback', label: 'Roll back to 2.3.7', state: 'running' }] } },
    { wait: 1800, patch: { status: 'failed', status_text: 'Rolled back: production serves 2.3.7', log: null,
      steps: [...plan(['done', 'done', 'done', 'failed'], { ...DONE3, prod: 'lock timeout on table sessions' }), { id: 'rollback', label: 'Roll back to 2.3.7', state: 'done', detail: 'serving 2.3.7' }],
      explanation: 'The 2.4.0 deploy failed (lock timeout on table sessions). Its migrations were reverted and production serves 2.3.7 again.' } },
  ],
}

// --- Slow machine -------------------------------------------------------------------------------
const mplan = (states, details = {}) => [
  ['stats', 'Measure CPU and memory'], ['procs', 'Find the heaviest processes'], ['fix', 'Stop the culprit'], ['verify', 'Check that it recovered'],
].map(([id, label], i) => ({ id, label, state: states[i] || 'pending', ...(details[id] ? { detail: details[id] } : {}) }))
const HOT = [{ label: 'memory', value: '15.6 / 16 GB', tone: 'bad' }, { label: 'CPU', value: '97%', tone: 'bad' }, { label: 'swap', value: '7.9 GB', tone: 'warn' }]
const PROCS = (stopped) => [
  { id: '8812', label: 'node · next dev (acme-webapp)', detail: stopped ? 'stopped' : '182% CPU · up 3d 4h', value: '9.4 GB', tone: stopped ? 'neutral' : 'bad' },
  { id: '412', label: 'postgres · docker: prod-replica', detail: '41% CPU · up 12d · kept, as you asked', value: '2.1 GB', tone: 'neutral' },
  { id: '2210', label: 'chrome · 38 tabs', detail: '12% CPU · up 1d', value: '1.6 GB', tone: 'neutral' },
  { id: '3051', label: 'code · VS Code', detail: '6% CPU · up 1d', value: '0.9 GB', tone: 'neutral' },
]
const MACHINE = {
  label: 'Slow machine · find and stop the culprit', type: 'task_card',
  ask: 'My workstation is freezing and the fans are at max. Find out what’s eating it and fix it, but don’t touch the prod-replica database.',
  steps: [
    { wait: 700, show: { title: 'Why dev-ws-07 is freezing', subtitle: 'Ubuntu 24.04 · 8 cores · 16 GB', status: 'running', status_text: 'Measuring CPU and memory', steps: mplan(['running']) } },
    { wait: 1500, patch: { status_text: 'Finding the heaviest processes', metrics: HOT, steps: mplan(['done', 'running'], { stats: 'CPU 97%' }) } },
    { wait: 1900, patch: { status: 'waiting', status_text: 'Waiting for your go', items: PROCS(false), steps: mplan(['done', 'done'], { stats: 'CPU 97%', procs: '4 checked' }),
      explanation: 'The next dev server (node, pid 8812) holds 9.4 GB and its memory grew about 300 MB per hour. Stopping it frees the memory; unsaved work in it is lost. The prod-replica database is left alone.',
      actions: [{ id: 'stop_8812', label: 'Stop node (pid 8812)', kind: 'danger', busy_label: 'Stopping' }] } },
    { await: 'stop_8812' },
    { wait: 450, patch: { status: 'running', status_text: 'Stopping node (pid 8812)', explanation: null, actions: [], steps: mplan(['done', 'done', 'running'], { stats: 'CPU 97%', procs: '4 checked' }) } },
    { wait: 1300, patch: { status_text: 'Checking that it recovered', items: PROCS(true), steps: mplan(['done', 'done', 'done', 'running'], { stats: 'CPU 97%', procs: '4 checked', fix: '9.1 GB freed' }) } },
    { wait: 1500, patch: { status: 'done', status_text: 'Back to normal: 6.2 / 16 GB used, CPU 18%',
      metrics: [{ label: 'memory', value: '6.2 / 16 GB', tone: 'good' }, { label: 'CPU', value: '18%', tone: 'good' }, { label: 'swap', value: '1.1 GB', tone: 'good' }],
      steps: mplan(['done', 'done', 'done', 'done'], { stats: 'CPU 97%', procs: '4 checked', fix: '9.1 GB freed', verify: 'CPU 18%' }) } },
  ],
}

// --- Cleanup ------------------------------------------------------------------------------------
const FILES = [
  { id: 'backup-old-laptop.zip', detail: 'modified 2 years ago', size_mb: 11161.6, tag: 'old', selected: true },
  { id: 'ubuntu-24.04-desktop-amd64.iso', detail: 'modified 8 months ago', size_mb: 5836.8, tag: 'old', selected: true },
  { id: 'zoom-recording-2026-03-14.mp4', detail: 'modified 8 months ago', size_mb: 2252.8, tag: 'old', selected: true },
  { id: 'Screen Recording 2026-11-08.mov', detail: 'modified yesterday', size_mb: 640, tag: 'recent', selected: false },
  { id: 'node-v18.17.0.pkg', detail: 'modified 1 year ago', size_mb: 96, tag: 'old', selected: true },
  { id: 'tax-return-2025.pdf', detail: 'modified 3 weeks ago', size_mb: 3, tag: 'recent', selected: false },
  { id: 'invoice-acme-oct.pdf', detail: 'modified 5 days ago', size_mb: 0.4, tag: 'open', tone: 'warn', locked: true, selected: false },
].map((f) => ({ label: f.id, tone: 'neutral', ...f }))
const picked = (ctx) => (ctx.values.selected || []).map(String)
const cleanup = (inUse) => ({
  label: inUse ? 'Cleanup · a file in use is reported' : 'Cleanup · free up space in Downloads', type: 'review_list',
  ask: 'My disk is almost full. Can you free up some space in my Downloads folder?',
  steps: [
    { wait: 700, show: { title: 'Free up space in Downloads', subtitle: '~/Downloads · 3.1 GB free on disk', status: 'scanning', status_text: 'Scanning ~/Downloads', items: [] } },
    { wait: 1700, patch: { status: 'review', status_text: 'Pick what to delete', items: FILES, summary: { total_mb: 20070 },
      explanation: 'Ticked: 4 files older than a few months that nothing has open (18.9 GB). Recent recordings and documents stay unticked.',
      actions: [{ id: 'delete_selected', label: 'Delete selected', kind: 'danger', busy_label: 'Deleting' }] } },
    { await: 'delete_selected' },
    { wait: 450, patch: (ctx) => ({ status: 'applying', status_text: `Deleting ${picked(ctx).length} of ${FILES.length}`, explanation: null, actions: [] }) },
    { wait: 1700, patch: (ctx) => {
      const sel = picked(ctx)
      const fails = inUse ? sel.filter((id) => id === 'backup-old-laptop.zip') : []
      const items = FILES.map((f) => sel.includes(f.id)
        ? (fails.includes(f.id) ? { ...f, state: 'failed', detail: 'file is open in another program (Archive Manager)', tone: 'bad' } : { ...f, state: 'done' })
        : f)
      const freed = FILES.filter((f) => sel.includes(f.id) && !fails.includes(f.id)).reduce((t, f) => t + f.size_mb, 0)
      return { status: 'done', items, summary: { freed_mb: freed },
        status_text: `Freed ${gb(freed)}${fails.length ? ` · ${fails.length} file not deleted` : ''}`,
        ...(fails.length ? { explanation: `${fails[0]} was not deleted: it is open in another program (Archive Manager). Close it and I can try again.` } : {}) }
    } },
  ],
})

// --- Study ------------------------------------------------------------------------------------------
const opts = (...labels) => labels.map((label, i) => ({ id: 'abcd'[i], label }))
const DIAGNOSTIC = [
  { id: 'q1', topic: 'timeouts', prompt: 'Why does Raft randomize election timeouts?',
    options: opts('So split votes are unlikely to repeat', 'To spread load across followers', 'So the leader spots slow followers', 'To pace log replication'),
    answer: 'a', explain: 'With random timeouts one server usually times out first, asks for votes and wins before the others start.' },
  { id: 'q2', topic: 'split', prompt: 'Two candidates run in the same term and neither gets a majority. What happens next?',
    options: opts('The candidate with the higher id wins', 'Both step down and the old leader resumes', 'They time out and a new election starts in a higher term', 'The cluster waits for an operator'),
    answer: 'c', explain: 'Nobody wins that term: a candidate times out again, bumps the term and starts a new election.' },
  { id: 'q3', topic: 'terms', prompt: 'A leader gets an AppendEntries reply carrying a higher term. It…',
    options: opts('ignores it: it is the leader', 'steps down to follower and adopts that term', 'starts a new election at once', 'retries with its own term'),
    answer: 'b', explain: 'Any higher term means its leadership is stale: it becomes a follower in the newer term.' },
  { id: 'q4', topic: 'votes', prompt: 'How many votes can a server grant in one term?',
    options: opts('One, first come first served', 'One per candidate', 'One per candidate with an up-to-date log', 'As many as needed until a leader exists'),
    answer: 'a', explain: 'One vote per term, persisted to disk, is what makes two leaders in one term impossible.' },
  { id: 'q5', topic: 'log', prompt: 'A voter refuses a candidate whose log is…',
    options: opts('shorter than its own, whatever the terms', 'less up to date: an older last term, or the same last term and shorter', 'from a term older than the voter’s current term', 'missing uncommitted entries'),
    answer: 'b', explain: 'Up to date means the last entry’s term first, then the length: so a new leader always holds every committed entry.' },
]
const BANK = {
  split: [
    { id: 'r_split1', topic: 'split', prompt: 'Without randomized timeouts, why could split votes go on forever?',
      options: opts('Candidates would keep timing out together and splitting the votes again', 'Terms would stop increasing', 'Followers would reject every RequestVote', 'Logs would be truncated each round'),
      answer: 'a', explain: 'Synchronized candidates collide every round; randomness breaks the tie.' },
    { id: 'r_split2', topic: 'split', prompt: 'After a split vote, what goes up before the next election?',
      options: opts('The commit index', 'The current term', 'The base election timeout', 'The number of voters'),
      answer: 'b', explain: 'Each new election runs in a new, higher term.' },
  ],
  log: [
    { id: 'r_log1', topic: 'log', prompt: 'Candidate C’s last entry is (term 4, index 9); voter V’s is (term 5, index 6). Does V vote for C?',
      options: opts('Yes, C’s log is longer', 'No, V’s last term is higher', 'Yes, if C’s current term is higher', 'No, logs must be identical'),
      answer: 'b', explain: 'The last term is compared first: 5 beats 4, whatever the lengths.' },
    { id: 'r_log2', topic: 'log', prompt: 'Why can only up-to-date candidates win?',
      options: opts('It makes elections faster', 'So a new leader holds every committed entry', 'To keep terms in sync', 'To cut network traffic'),
      answer: 'b', explain: 'A committed entry is on a majority, and a winner needs a majority whose logs are no newer than its own.' },
  ],
  terms: [{ id: 'r_terms', topic: 'terms', prompt: 'A server sees a higher term in any RPC. It…',
    options: opts('becomes a follower and adopts the term', 'starts an election', 'ignores it', 'rejects only that RPC'), answer: 'a', explain: 'Terms act as a logical clock: the highest one wins everywhere.' }],
  votes: [{ id: 'r_votes', topic: 'votes', prompt: 'A server already voted in term 7. Another candidate in term 7 asks. It…',
    options: opts('votes again if that log is newer', 'refuses: one vote per term', 'switches its vote', 'starts its own election'), answer: 'b', explain: 'The vote for term 7 is spent; it is persisted so a restart cannot reuse it.' }],
  timeouts: [{ id: 'r_timeouts', topic: 'timeouts', prompt: 'Typical Raft election timeouts are…',
    options: opts('fixed at one second', 'random in a range like 150–300 ms', 'equal to the heartbeat interval', 'chosen by the leader'), answer: 'b', explain: 'Random, and well above the heartbeat interval so a live leader keeps followers quiet.' }],
}
const TOPICS = [['timeouts', 'Randomized timeouts'], ['split', 'Split votes'], ['terms', 'Terms'], ['votes', 'One vote per term'], ['log', 'Up-to-date log check']]
const splan = (states, details = {}) => [
  ['diag', 'Diagnostic · 5 questions'], ['gaps', 'Find the weak spots'], ['lesson', 'Short lesson'], ['retest', 'Re-test the weak spots'], ['reviews', 'Plan the reviews'],
].map(([id, label], i) => ({ id, label, state: states[i] || 'pending', ...(details[id] ? { detail: details[id] } : {}) }))
const missedTopics = (ctx, qs) => [...new Set(qs.filter((q) => (ctx.values.answers || {})[q.id] !== q.answer).map((q) => q.topic))]
const weak = (ctx) => { const m = missedTopics(ctx, DIAGNOSTIC); return m.length ? m.slice(0, 2) : ['split', 'log'] }
const masteryAfterDiag = (ctx) => TOPICS.map(([id, label]) => {
  const q = DIAGNOSTIC.find((x) => x.topic === id), ok = (ctx.values.answers || {})[q.id] === q.answer
  return { id, label, mastery: ok ? 0.85 : 0.3, note: ok ? 'right' : 'missed' }
})
const RETEST = (ctx) => {
  const w = ctx.weak || ['split', 'log'], qs = w.flatMap((t) => BANK[t])
  return qs.slice(0, 3).length >= 3 ? qs.slice(0, 3) : [...qs, ...BANK.split, ...BANK.log].filter((q, i, a) => a.indexOf(q) === i).slice(0, 3)
}
const LESSONS = {
  split: ['Each server votes once per term, so two candidates can split the votes and neither reaches a majority.',
    'Nobody wins that term: the candidates time out, bump the term and run a new election.',
    'Randomized timeouts (say 150–300 ms) make another collision unlikely: one usually starts first and wins.'],
  log: ['A voter compares last entries: the higher last term wins; with the same last term, the longer log wins.',
    'A committed entry sits on a majority, and a winner needs votes from a majority: so every leader holds every committed entry.'],
  terms: ['Terms are a logical clock: any RPC with a higher term turns the receiver into a follower of that term.'],
  votes: ['One vote per term, written to disk before replying: a restarted server cannot vote twice.'],
  timeouts: ['Election timeouts are random and well above the heartbeat interval, so a live leader keeps everyone quiet.'],
}
const CARDS = {
  timeouts: [{ front: 'Why are election timeouts random?', back: 'So one server usually times out first and wins before a split vote can form.' }],
  split: [{ front: 'What ends a split vote?', back: 'A new election in a higher term, after a randomized timeout.' }],
  log: [{ front: 'Who can win an election?', back: 'A candidate whose log is at least as up to date as a majority’s.' },
    { front: '(term 5, index 6) vs (term 4, index 9): which is more up to date?', back: 'Term 5: the last term is compared before the length.' }],
  terms: [{ front: 'A stale leader sees a higher term. It…', back: 'steps down to follower in that term.' }],
  votes: [{ front: 'How many votes per term?', back: 'One, written to disk before replying.' }],
}
const STUDY = {
  label: 'Study · midterm tomorrow on Raft elections', type: 'study_card',
  ask: 'I have my distributed systems midterm tomorrow morning and I still get confused about what happens when two candidates trigger an election at the same time. Test me.',
  steps: [
    { wait: 700, show: { title: 'Raft elections · midterm tomorrow', subtitle: 'Distributed systems · leader election', status: 'running',
      status_text: 'Writing your diagnostic', steps: splan(['running']) } },
    { wait: 1500, patch: { status: 'quiz', status_text: 'Answer the 5 questions in the card', quiz: { id: 'diagnostic', questions: DIAGNOSTIC },
      actions: [{ id: 'send_answers', label: 'Send my answers', busy_label: 'Grading' }] } },
    { await: 'send_answers' },
    { wait: 450, patch: (ctx) => ({ status: 'running', status_text: 'Grading your answers', quiz: null, actions: [],
      steps: splan(['done', 'running'], { diag: `${ctx.values.score}/${ctx.values.total}` }) }) },
    { wait: 1300, patch: (ctx) => ({ status_text: 'Writing a lesson on your weak spots', topics: masteryAfterDiag(ctx),
      steps: splan(['done', 'done', 'running'], { diag: `${ctx.values.score}/${ctx.values.total}`, gaps: `${missedTopics(ctx, DIAGNOSTIC).length || 'no'} weak spot${missedTopics(ctx, DIAGNOSTIC).length === 1 ? '' : 's'}` }) }) },
    { wait: 1800, patch: (ctx) => {
      // Later clicks replace ctx.values: keep what the diagnostic said.
      const w = (ctx.weak = weak(ctx)), label = TOPICS.find(([id]) => id === w[0])[1]
      ctx.diag = { score: ctx.values.score, total: ctx.values.total, gaps: missedTopics(ctx, DIAGNOSTIC).length }
      ctx.topicsAfterDiag = masteryAfterDiag(ctx)
      const labels = w.map((t) => TOPICS.find(([id]) => id === t)[1])
      return { status: 'waiting', status_text: 'Read it, then re-test', lesson: {
        title: labels.length > 1 ? `${labels[0]} and ${labels[1].toLowerCase()}, in a few ideas` : `${label}, in a few ideas`,
        points: w.flatMap((t) => LESSONS[t]).slice(0, 4),
        cards: [...w.flatMap((t) => CARDS[t]), ...CARDS.split, ...CARDS.terms].filter((c, i, a) => a.indexOf(c) === i).slice(0, 3) },
        steps: splan(['done', 'done', 'done'], { diag: `${ctx.diag.score}/${ctx.diag.total}`, gaps: `${ctx.diag.gaps || 'no'} weak spot${ctx.diag.gaps === 1 ? '' : 's'}`, lesson: '3 cards' }),
        actions: [{ id: 'retest', label: 'Re-test me', kind: 'primary', busy_label: 'Preparing' }] }
    } },
    { await: 'retest' },
    { wait: 900, patch: (ctx) => ({ status: 'quiz', status_text: 'Three questions on your weak spots', lesson: null, quiz: { id: 'retest', questions: RETEST(ctx) },
      steps: splan(['done', 'done', 'done', 'running'], { diag: `${ctx.diag.score}/${ctx.diag.total}`, gaps: `${ctx.diag.gaps || 'no'} weak spot${ctx.diag.gaps === 1 ? '' : 's'}`, lesson: '3 cards' }),
      actions: [{ id: 'send_retest', label: 'Send my answers', busy_label: 'Grading' }] }) },
    { await: 'send_retest' },
    { wait: 450, patch: (ctx) => {
      ctx.retest = { score: ctx.values.score, total: ctx.values.total, answers: ctx.values.answers || {} }
      return { status: 'running', status_text: 'Grading your answers', quiz: null, actions: [],
        steps: splan(['done', 'done', 'done', 'done', 'running'], { diag: `${ctx.diag.score}/${ctx.diag.total}`, gaps: `${ctx.diag.gaps || 'no'} weak spot${ctx.diag.gaps === 1 ? '' : 's'}`, lesson: '3 cards', retest: `${ctx.retest.score}/${ctx.retest.total}` }) }
    } },
    { wait: 1200, patch: (ctx) => {
      const answers = ctx.retest.answers, qs = RETEST(ctx)
      return { status: 'waiting', status_text: 'Plan your reviews',
        topics: (ctx.topicsAfterDiag || []).map((t) => {
          const mine = qs.filter((q) => q.topic === t.id)
          if (!mine.length) return t
          const ok = mine.filter((q) => answers[q.id] === q.answer).length / mine.length
          return { ...t, mastery: Math.min(0.95, 0.35 + ok * 0.55), note: ok === 1 ? 'fixed' : ok > 0 ? 'better' : 'still shaky' }
        }),
        schedule: [{ id: 'r1', when: 'Tomorrow 7:30', label: 'Before the exam · 3 cards', state: 'planned' },
          { id: 'r2', when: 'In 3 days', label: 'Raft elections · 8 questions', state: 'planned' },
          { id: 'r3', when: 'In a week', label: 'Whatever is still shaky', state: 'planned' }],
        explanation: 'Three short reviews, spaced out, are what makes this stick past tomorrow. I can set them as reminders here.',
        actions: [{ id: 'set_reminders', label: 'Set 3 reminders', kind: 'primary', busy_label: 'Scheduling' }] }
    } },
    { await: 'set_reminders' },
    { wait: 450, patch: { status: 'running', status_text: 'Scheduling your reminders', explanation: null, actions: [] } },
    { wait: 1300, patch: (ctx) => ({ status: 'done', status_text: '3 reminders set · the first one tomorrow at 7:30',
      schedule: [{ id: 'r1', when: 'Tomorrow 7:30', label: 'Before the exam · 3 cards', state: 'set' },
        { id: 'r2', when: 'In 3 days', label: 'Raft elections · 8 questions', state: 'set' },
        { id: 'r3', when: 'In a week', label: 'Whatever is still shaky', state: 'set' }],
      steps: splan(['done', 'done', 'done', 'done', 'done'], { diag: `${ctx.diag.score}/${ctx.diag.total}`, gaps: `${ctx.diag.gaps || 'no'} weak spot${ctx.diag.gaps === 1 ? '' : 's'}`, lesson: '3 cards', retest: `${ctx.retest.score}/${ctx.retest.total}`, reviews: '3 set' }) }) },
  ],
}

export const SCENARIOS = {
  study: STUDY,
  pr: PR,
  release: RELEASE,
  release_fail: RELEASE_FAIL,
  machine: MACHINE,
  cleanup: cleanup(false),
  cleanup_in_use: cleanup(true),
}
