"""Edit decisions for the v4 demo video: the v2 layout (the prompt typed in close-up, then WITH
GenUI beside WITHOUT it), cut tight: the wait before the card is one fast-forward, the card is
shown as it builds, and only the clicks and their results play at 1x.

Times are seconds into the recordings (demo/*_v2.mp4, not in git). "typing" rebuilds the prompt
being typed from a still of the composer: "base" is a frame with the whole prompt in the box and
"send" the last frame before it is sent, where the recording takes over.
"""

from scenes_v2 import CHAT, LEFT, PR as PR_V2, QUIZ, RELEASE as RELEASE_V2, RIGHT, STUDY as STUDY_V2

TOP = (700, 520, 1300)   # the sent message and the agent's first steps, top left

PR = {
    "src": "demo/pr_v2.mp4",
    "title": "Pull request",
    "typing": {"base": 8.4, "send": 8.67, "dur": 2.0},
    "segments": [
        {"src": (8.67, 9.3), "cam": TOP, "split": True, "trans": 0.6},   # sent
        {"src": (9.3, 34.4), "speed": 24},                                     # commit, push, open the PR, fetch main
        {"src": (34.4, 37.6), "speed": 1.3, "cam": LEFT, "trans": 0.5},        # the card builds: 4 conflicts, who changed what
        {"src": (37.6, 41.0), "speed": 4, "cam": RIGHT, "trans": 0.5},
        {"src": (41.0, 43.0)},                                                 # click: Combine both sides
        {"src": (43.0, 64.5), "speed": 20, "cam": CHAT, "trans": 0.5},         # resolving, pushing, checks
        {"src": (64.5, 66.3), "cam": LEFT, "trans": 0.5},                      # ready: 4 checks passed
        {"src": (66.3, 69.2), "speed": 4, "cam": RIGHT, "trans": 0.4},
        {"src": (69.2, 71.4)},                                                 # click: Merge
        {"src": (71.4, 74.4), "cam": LEFT, "trans": 0.5},                      # merged: the graph turns purple
    ],
    "sim": PR_V2["sim"],
}

RELEASE = {
    "src": "demo/push_v2.mp4",
    "title": "Release",
    "typing": {"base": 0.6, "send": 0.93, "dur": 1.1},
    "segments": [
        {"src": (0.93, 1.5), "cam": TOP, "split": True, "trans": 0.6},   # sent
        {"src": (1.5, 33.2), "speed": 30},                                     # build, staging, smoke tests
        {"src": (33.2, 34.6), "cam": LEFT, "trans": 0.5},                      # the card: waiting for your go
        {"src": (34.6, 35.8), "speed": 2, "cam": RIGHT, "trans": 0.5},
        {"src": (35.8, 37.8)},                                                 # click: Deploy 2.4.0 to production
        {"src": (37.8, 51.4), "speed": 14, "cam": CHAT, "trans": 0.5},         # deploying
        {"src": (51.4, 53.6), "cam": LEFT, "trans": 0.5},                      # migration 0042 fails: red
        {"src": (53.6, 56.4), "speed": 4, "cam": RIGHT, "trans": 0.5},
        {"src": (56.4, 58.4)},                                                 # click: Roll back
        {"src": (58.4, 64.6), "speed": 8, "cam": CHAT, "trans": 0.5},
        {"src": (64.6, 67.6), "cam": LEFT, "trans": 0.5},                      # the rollback branches off the failed step
    ],
    "sim": RELEASE_V2["sim"],
}

STUDY = {
    "src": "demo/exam_v2.mp4",
    "title": "Study session",
    "typing": {"base": 1.0, "send": 2.40, "dur": 1.7},
    "segments": [
        {"src": (2.40, 3.0), "cam": TOP, "split": True, "trans": 0.6},   # sent
        {"src": (3.0, 17.0), "speed": 14},                                     # writing the quiz
        {"src": (17.0, 18.4), "cam": QUIZ, "trans": 0.5},                      # the card builds: a quiz
        {"src": (18.4, 24.4), "speed": 4},
        {"src": (24.4, 28.6), "speed": 1.2},                                   # first answer: green, red, the why
        {"src": (28.6, 59.0), "speed": 20},                                    # the next questions
        {"src": (59.0, 61.6), "speed": 1.3},                                   # last answer
        {"src": (61.6, 64.6)},                                                 # the score counts up
    ],
    "sim": STUDY_V2["sim"],
}

SCENES = [PR, RELEASE, STUDY]
