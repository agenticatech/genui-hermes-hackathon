"""Edit decisions for the v2 demo video: three real Hermes Desktop runs with GenUI (demo/*_v2.mp4,
not in git), each beside a simulation of the same run without it (sim_v2.html), timed on the
recording's own clock (seconds into the raw video).

Cameras are (centre x, centre y, width) in recording pixels; the height follows the panel's shape,
and a camera may reach past the recording's edges (the app's background fills in). "chat" frames
the whole conversation column, "right" the card's pill and status line, "left" its graph and rows.
The simulation reuses the agent's own words from the real run, minus the card: each decision
becomes a reply the user has to type.
"""

CHAT = (985, 640, 1890)
CHAT_TOP = (985, 560, 1890)
RIGHT = (1430, 520, 1060)
LEFT = (640, 420, 1180)
INPUT = (760, 1190, 1500)
QUIZ = (700, 470, 1320)

PR = {
    "src": "demo/pr_v2.mp4",
    "title": "Pull request",
    "caption": "“Create the PR for my session refresh work”",
    "segments": [
        # (Before 7.5 s a composer tooltip shows a local file path: the scene starts after it.)
        {"src": (7.5, 8.6), "cam": INPUT, "trans": 0},                                      # the prompt, pasted
        {"src": (8.6, 9.6), "cam": CHAT_TOP, "split": True, "trans": 1.0},                   # sent
        {"src": (9.6, 33.0), "speed": 12},                                                   # commit, push, open the PR, fetch main
        {"src": (33.0, 35.0), "cam": CHAT, "trans": 0.6},                                    # the card builds
        {"src": (35.0, 40.6), "cam": LEFT, "trans": 0.8, "speed": 1.4},                      # 4 conflicts: the commits, who changed what
        {"src": (40.6, 44.0), "cam": RIGHT, "trans": 0.7},                                   # click: Combine both sides
        {"src": (44.0, 64.5), "speed": 10, "cam": CHAT, "trans": 0.8},                        # resolving, pushing, checks
        {"src": (64.5, 67.0), "cam": LEFT, "trans": 0.7},                                    # ready: 4 checks passed
        {"src": (67.0, 69.0), "speed": 3, "cam": RIGHT, "trans": 0.6},
        {"src": (69.0, 71.5), "cam": RIGHT},                                                 # click: Merge
        {"src": (71.5, 74.5), "cam": LEFT, "trans": 0.7},                                    # merged: the graph turns purple
        {"src": (74.5, 75.4), "cam": CHAT, "trans": 0.8},
        {"hold_at": 75.4, "dur": 1.0},
    ],
    "sim": [
        {"t": 8.4, "type": "bubble", "text": "Create the PR for my session refresh work in ~/genui-sandbox/webapp. There's no GitHub CLI on this machine: use ~/genui-sandbox/bin/pr instead of gh pr (create, view, checks, merge)."},
        {"t": 9.6, "type": "activity", "text": "Running git status · git add -A · git commit"},
        {"t": 14.0, "type": "activity", "text": "Running git push -u origin feat/session-refresh"},
        {"t": 18.5, "type": "activity", "text": "Running pr create --title \"Refresh sessions near expiry\""},
        {"t": 23.5, "type": "activity", "text": "Running git fetch origin · git merge-tree origin/main HEAD"},
        {"t": 28.5, "type": "activity", "text": "Thinking"},
        {"t": 33.2, "type": "row", "text": "Ran 6 commands"},
        {"t": 33.4, "type": "say", "dur": 2.4, "text":
            "I opened PR #128, but its checks can't run yet: it has merge conflicts with `main`.\n\n"
            "**What's blocking it:** Lena Park pushed key-rotation changes to `main` about 20 minutes ago. They touch "
            "the same lines as yours, giving 4 conflicts in `src/auth.ts` and `src/middleware.ts`.\n\n"
            "**My proposed fix:** keep her new keys and wrap them with your refresh logic, and keep both imports.\n\n"
            "Reply **\"combine\"** to resolve them that way, or **\"myself\"** if you'd rather do it."},
        {"t": 39.4, "type": "type", "dur": 1.1, "text": "combine"},
        {"t": 41.0, "type": "send"},
        {"t": 41.0, "type": "bubble", "text": "combine"},
        {"t": 42.2, "type": "activity", "text": "Running git merge origin/main · editing src/auth.ts, src/middleware.ts"},
        {"t": 52.0, "type": "activity", "text": "Running git push · pr checks"},
        {"t": 64.3, "type": "row", "text": "Ran 5 commands"},
        {"t": 64.5, "type": "say", "dur": 1.8, "text":
            "I resolved all 4 conflicts by combining both sides. The merge is pushed as `81c1206`, and all 4 checks on "
            "PR #128 passed: tests (42 passed), lint, types and the preview deploy.\n\n"
            "Reply **\"merge\"** to merge PR #128 into `main`."},
        {"t": 67.6, "type": "type", "dur": 0.9, "text": "merge"},
        {"t": 69.2, "type": "send"},
        {"t": 69.2, "type": "bubble", "text": "merge"},
        {"t": 70.0, "type": "activity", "text": "Running pr merge"},
        {"t": 73.6, "type": "say", "dur": 1.0, "text": "PR #128 is merged, so session refresh is now in `main` as `812b1b6`."},
    ],
}

RELEASE = {
    "src": "demo/push_v2.mp4",
    "title": "Release",
    "caption": "“Ship release 2.4.0 to production”",
    "segments": [
        {"src": (0.0, 1.6), "cam": INPUT, "trans": 0},                                      # the prompt, sent
        {"src": (1.6, 32.4), "speed": 12, "cam": CHAT_TOP, "split": True, "trans": 1.0},     # build, staging, smoke tests
        {"src": (32.4, 34.0), "cam": CHAT, "trans": 0.6},                                    # the card arrives
        {"src": (34.0, 35.8), "cam": LEFT, "trans": 0.7},                                    # waiting for your go
        {"src": (35.8, 38.6), "cam": RIGHT, "trans": 0.7},                                   # click: Deploy 2.4.0 to production
        {"src": (38.6, 51.4), "speed": 7, "cam": CHAT, "trans": 0.8},                        # deploying
        {"src": (51.4, 54.2), "cam": LEFT, "trans": 0.6},                                    # migration 0042 fails: red
        {"src": (54.2, 56.4), "speed": 3, "cam": RIGHT, "trans": 0.7},
        {"src": (56.4, 58.6), "cam": RIGHT},                                                 # click: Roll back migration 0041
        {"src": (58.6, 64.6), "speed": 6, "cam": CHAT, "trans": 0.8},
        {"src": (64.6, 67.4), "cam": LEFT, "trans": 0.6},                                    # the rollback branches off
        {"src": (67.4, 75.6), "speed": 7},
        {"src": (75.6, 77.4)},                                                               # rolled back, healthy on 2.3.7
        {"src": (77.4, 78.4), "cam": CHAT, "trans": 0.8},
        {"hold_at": 78.4, "dur": 0.6},
    ],
    "sim": [
        {"t": 0.9, "type": "bubble", "text": "Ship release 2.4.0 to production with ~/genui-sandbox/release/release.sh."},
        {"t": 2.0, "type": "activity", "text": "Running ./release.sh build 2.4.0"},
        {"t": 10.0, "type": "activity", "text": "Running ./release.sh staging 2.4.0"},
        {"t": 18.0, "type": "activity", "text": "Running ./release.sh smoke 2.4.0"},
        {"t": 27.0, "type": "activity", "text": "Thinking"},
        {"t": 32.4, "type": "row", "text": "Ran 4 commands"},
        {"t": 32.6, "type": "say", "dur": 1.6, "text":
            "I haven't deployed 2.4.0 to production yet.\n\n"
            "The build worked and 2.4.0 is running on staging (3 of 3 pods ready). All 18 smoke tests passed.\n\n"
            "The production deploy will replace 2.3.7 on all 8 pods and run two database migrations, "
            "`0041_rotate_keys` and `0042_add_session_index`. Reply **\"deploy\"** to go ahead."},
        {"t": 35.6, "type": "type", "dur": 1.0, "text": "deploy"},
        {"t": 37.0, "type": "send"},
        {"t": 37.0, "type": "bubble", "text": "deploy"},
        {"t": 38.0, "type": "activity", "text": "Running ./release.sh prod 2.4.0"},
        {"t": 51.6, "type": "say", "dur": 1.6, "text":
            "The production deploy failed, so 2.4.0 did not ship.\n\n"
            "• **What happened:** migration `0042_add_session_index` stopped on a lock timeout. The `sessions` table was "
            "locked by process 3317, a long-running analytics export.\n"
            "• **Where production is now:** it still serves 2.3.7, but `0041_rotate_keys` stayed applied.\n"
            "• **The fix:** roll back. Reply **\"rollback\"** to undo `0041_rotate_keys`."},
        {"t": 55.0, "type": "type", "dur": 1.2, "text": "rollback"},
        {"t": 56.8, "type": "send"},
        {"t": 56.8, "type": "bubble", "text": "rollback"},
        {"t": 57.6, "type": "activity", "text": "Running ./release.sh rollback 2.4.0 · ./release.sh health"},
        {"t": 75.6, "type": "say", "dur": 1.4, "text":
            "The rollback worked: production is healthy on 2.3.7 (0.1% errors, p95 180 ms). Release 2.4.0 has still not shipped."},
    ],
}

STUDY = {
    "src": "demo/exam_v2.mp4",
    "title": "Study session",
    "caption": "“My stats midterm is tomorrow. Test me.”",
    "segments": [
        {"src": (1.4, 3.4), "cam": INPUT, "trans": 0},                                      # the prompt, sent
        {"src": (3.4, 16.6), "speed": 10, "cam": CHAT_TOP, "split": True, "trans": 1.0},     # writing the quiz
        {"src": (16.6, 18.4), "cam": CHAT, "trans": 0.6},                                    # the card builds: a quiz
        {"src": (18.4, 24.6), "speed": 3, "cam": QUIZ, "trans": 0.8},
        {"src": (24.6, 30.4), "speed": 1.2},                                                 # first answer: green, red, why
        {"src": (30.4, 58.0), "speed": 6},                                                   # the next questions
        {"src": (58.0, 63.6), "speed": 1.2},                                                 # last answer, the score counts up
        {"src": (63.6, 65.6), "cam": CHAT, "trans": 0.8},
        {"hold_at": 65.6, "dur": 1.0},
    ],
    "sim": [
        {"t": 2.6, "type": "bubble", "text": "I have my level 1 statistics midterm tomorrow morning and I still get confused about what accuracy, recall and precision. Test me."},
        {"t": 3.4, "type": "activity", "text": "Thinking"},
        {"t": 16.6, "type": "say", "dur": 3.4, "text":
            "Here are 6 questions. Reply with your answers, like 1a 2b 3c.\n\n"
            "**1.** Precision answers which question?\n a) Of all actual positives, how many did we catch?\n"
            " b) Of all predicted positives, how many are truly positive?\n c) Of all predictions, how many are correct?\n\n"
            "**2.** Recall answers which question?\n a) Of all actual positives, how many did we catch?\n"
            " b) Of all predicted positives, how many are truly positive?\n c) Of all actual negatives, how many did we reject?\n\n"
            "**3.** A disease test on 100 people: TP=8, FN=2, FP=12, TN=78. Accuracy?\n a) 0.80   b) 0.86   c) 0.40   d) 0.08\n\n"
            "**4.** Same test. Precision?\n a) 0.80   b) 0.40   c) 0.86   d) 0.67\n\n"
            "**5.** Same test. Recall?\n a) 0.40   b) 0.86   c) 0.80   d) 0.12\n\n"
            "**6.** Only 1% of emails are fraud. A model that says \"not fraud\" every time has 99% accuracy. What is its recall?\n"
            " a) 99%   b) 1%   c) 0%   d) undefined"},
        {"t": 38.0, "type": "type", "dur": 5.0, "text": "1b 2a 3a 4b 5b 6a"},
        {"t": 45.0, "type": "send"},
        {"t": 45.0, "type": "bubble", "text": "1b 2a 3a 4b 5b 6a"},
        {"t": 46.0, "type": "activity", "text": "Thinking"},
        {"t": 52.0, "type": "say", "dur": 2.2, "text":
            "You got **3 of 6** right. You missed:\n"
            "• **3:** accuracy is (8 + 78) / 100 = 0.86, not 0.80.\n"
            "• **5:** recall is 8 / (8 + 2) = 0.80.\n"
            "• **6:** recall is 0%: the model never catches a single fraud.\n\n"
            "Want me to go over recall again?"},
    ],
}

SCENES = [PR, RELEASE, STUDY]
