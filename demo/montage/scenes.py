"""Edit decisions per recording: where the camera looks, what plays at which speed, and the
simulated run without GenUI, timed on the recording's own clock (seconds into the raw video).

Cameras are (centre x, centre y, width) in recording pixels; the height follows the panel's shape.
The simulation reuses the agent's own words from the real run, minus the card: the decision becomes
a reply the user has to type.
"""

CAMS = {
    "input": (790, 1136, 960),    # the prompt box, close; its bottom stays above the status bar (y 1414)
    "full": (1279, 705, 2508),    # the whole app, status bar left out
    "chat": (840, 560, 1000),     # the conversation, for the split screen's left panel
}

PUSH_TO_PROD = {
    "src": "demo/with_push_to_prod.mp4",
    "prompt": "Ship release 2.4.0 to production with ~/genui-sandbox/release/release.sh.",
    "base_t": 0.3,      # prompt box still empty
    "bubble_t": 4.0,    # the sent message, whose glyphs are reused for the typing
    "cams": CAMS,
    "segments": [
        {"typing": 2.2, "hold": 0.35, "cam": "input", "trans": 0},
        {"src": (1.65, 3.4), "cam": "full", "trans": 0.9},
        {"src": (3.4, 5.2), "cam": "chat", "split": True, "trans": 1.0},
        {"src": (5.2, 31.2), "speed": 8},                 # the agent builds, stages, runs smoke tests
        {"src": (31.2, 35.6)},                            # the card and the agent's reply arrive
        {"src": (35.6, 40.1), "speed": 3},                # the user reads
        {"src": (40.1, 43.6)},                            # the click
        {"src": (43.6, 60.7), "speed": 3},                # deploy and health check, live on the card
        {"src": (60.7, 62.3)},                            # the final reply
        {"hold_at": 64.8, "dur": 2.2},
    ],
    "sim": [
        {"t": 1.8, "type": "bubble", "text": "Ship release 2.4.0 to production with ~/genui-sandbox/release/release.sh."},
        {"t": 3.2, "type": "activity", "text": "Running cat ~/genui-sandbox/release/release.sh"},
        {"t": 8.5, "type": "activity", "text": "Running ./release.sh build 2.4.0 · 2 commands"},
        {"t": 14.5, "type": "activity", "text": "Running ./release.sh staging 2.4.0 · 3 commands"},
        {"t": 21.0, "type": "activity", "text": "Running ./release.sh smoke 2.4.0 · 4 commands"},
        {"t": 27.5, "type": "activity", "text": "Thinking"},
        {"t": 33.3, "type": "row", "text": "Ran 4 commands, used 5 tools"},
        {"t": 33.3, "type": "row", "text": "Thought ›"},
        {"t": 33.5, "type": "say", "dur": 1.8, "text":
            "I've built 2.4.0 and deployed it to staging, and all 18 smoke tests passed. I haven't deployed to "
            "production yet. That step replaces the live version for every user and runs database migrations, "
            "which may be hard to undo. **Reply \"deploy\" to go ahead**; a health check runs right after."},
        {"t": 40.3, "type": "type", "dur": 1.2, "text": "deploy"},
        {"t": 41.9, "type": "send"},
        {"t": 41.9, "type": "bubble", "text": "deploy"},
        {"t": 43.0, "type": "activity", "text": "Running ./release.sh prod 2.4.0"},
        {"t": 52.5, "type": "activity", "text": "Running ./release.sh health 2.4.0 · 2 commands"},
        {"t": 60.9, "type": "row", "text": "Ran 2 commands, used 3 tools"},
        {"t": 61.1, "type": "say", "dur": 1.2, "text":
            "Version 2.4.0 is live in production and the health check passed. The deploy also applied database "
            "migrations 0041 and 0042. After the deploy, the error rate is 0.2% and p95 latency is 182 ms."},
    ],
}

FREE_SPACE = {
    "src": "demo/with_free_space.mp4",
    "prompt": "My disk is getting full. Can you free up some space in ~/genui-sandbox/Downloads?",
    "base_t": 0.5,
    "bubble_t": 4.0,
    "cams": {**CAMS, "input": (830, 1119, 1020)},
    "segments": [
        {"typing": 2.4, "hold": 0.35, "cam": "input", "trans": 0},
        {"src": (1.0, 2.8), "cam": "full", "trans": 0.9},
        {"src": (2.8, 4.2), "cam": "chat", "split": True, "trans": 1.0},
        {"src": (4.2, 11.8), "speed": 6},                 # the agent lists the folder
        {"src": (11.8, 14.2)},                            # reply and card arrive
        {"src": (14.2, 20.4), "speed": 1.5},              # the user unticks the ISO, ticks the recording, clicks
        {"src": (20.4, 27.4), "speed": 4},                # deletion
        {"src": (27.4, 29.2)},                            # the final reply
        {"hold_at": 30.9, "dur": 2.2},
    ],
    "sim": [
        {"t": 1.2, "type": "bubble", "text": "My disk is getting full. Can you free up some space in ~/genui-sandbox/Downloads?"},
        {"t": 2.4, "type": "activity", "text": "Running ls -la ~/genui-sandbox/Downloads"},
        {"t": 6.5, "type": "activity", "text": "Running du -h ~/genui-sandbox/Downloads/* · 2 commands"},
        {"t": 11.9, "type": "row", "text": "Ran 1 command, used 2 tools"},
        {"t": 12.0, "type": "say", "dur": 2.6, "text":
            "I found 4 files using 251 MB in Downloads. I haven't deleted anything yet.\n\n"
            "1. ubuntu-24.04-desktop-amd64.iso, 150 MB: you can download it again anytime, I'd delete it.\n"
            "2. zoom-recording-2026-03-14.mp4, 80 MB: may be your only copy.\n"
            "3. Screen Recording 2026-11-08.mov, 20 MB, yesterday: may be your only copy.\n"
            "4. tax-return-2025.pdf: important, I won't touch it.\n\n"
            "**Tell me which files to delete**, for example \"delete 1\"."},
        {"t": 14.6, "type": "type", "dur": 4.6, "text": "delete 2 only, keep the iso"},
        {"t": 19.9, "type": "send"},
        {"t": 19.9, "type": "bubble", "text": "delete 2 only, keep the iso"},
        {"t": 21.0, "type": "activity", "text": "Running rm ~/genui-sandbox/Downloads/zoom-recording-2026-03-14.mp4"},
        {"t": 27.6, "type": "row", "text": "Ran 1 command, used 2 tools"},
        {"t": 27.7, "type": "say", "dur": 1.4, "text":
            "I deleted zoom-recording-2026-03-14.mp4, which freed 80 MB. Downloads is now down to 171 MB from 251 MB.\n\n"
            "The other three files are still there. If you need more space, deleting the 150 MB Ubuntu ISO would free "
            "the most, and you can download it again anytime."},
    ],
}

FREE_MEMORY = {
    "src": "demo/with_free_memory.mp4",
    "prompt": "My server feels slow. Find what’s eating memory and fix it, but don’t touch Hermes itself.",
    "base_t": 0.3,
    "bubble_t": 4.0,
    "cams": {**CAMS, "input": (860, 1102, 1080), "chat_low": (840, 700, 1000)},
    "segments": [
        {"typing": 2.6, "hold": 0.35, "cam": "input", "trans": 0},
        {"src": (1.3, 3.0), "cam": "full", "trans": 0.9},
        {"src": (3.0, 4.6), "cam": "chat", "split": True, "trans": 1.0},
        {"src": (4.6, 19.4), "speed": 8},                 # the agent measures memory and lists processes
        {"src": (19.4, 23.0)},                            # card and reply arrive
        {"src": (44.5, 48.4), "speed": 1.5, "trans": 0},  # (23 s of reading cut) the user reaches for the button
        {"src": (48.4, 50.8)},                            # the click
        {"src": (50.8, 58.9), "speed": 3, "cam": "chat_low", "trans": 1.4},  # stop and re-measure, live on the card
        {"src": (58.9, 61.9)},                            # the final reply
        {"hold_at": 61.9, "dur": 2.2},
    ],
    "sim": [
        {"t": 1.6, "type": "bubble", "text": "My server feels slow. Find what’s eating memory and fix it, but don’t touch Hermes itself."},
        {"t": 3.0, "type": "activity", "text": "Running free -m"},
        {"t": 7.0, "type": "activity", "text": "Running ps aux --sort=-%mem | head -15 · 2 commands"},
        {"t": 12.5, "type": "activity", "text": "Thinking"},
        {"t": 19.6, "type": "row", "text": "Ran 1 command, used 1 tool"},
        {"t": 19.6, "type": "row", "text": "Thought ›"},
        {"t": 19.8, "type": "say", "dur": 3.0, "text":
            "I found what's using the memory: a stray python3 script (PID 495913) holding about 165 MB. That's roughly "
            "18% of the server's 927 MB of RAM. All it does is reserve 200 MB and then sit idle for an hour, and it "
            "started 26 seconds before I checked.\n\n"
            "Right now only about 220 MB of RAM is free and 593 MB of swap is in use, which explains the slowness. The "
            "two Hermes processes use about 417 MB together, and I've left them alone.\n\n"
            "I haven't stopped it yet because ending a process can't be undone. If you didn't start it on purpose, "
            "**reply \"stop it\"** and I'll stop it and check that the memory comes back."},
        {"t": 46.6, "type": "type", "dur": 1.4, "text": "stop it"},
        {"t": 49.3, "type": "send"},
        {"t": 49.3, "type": "bubble", "text": "stop it"},
        {"t": 50.6, "type": "activity", "text": "Running kill 495913"},
        {"t": 54.0, "type": "activity", "text": "Running free -m · 2 commands"},
        {"t": 59.0, "type": "row", "text": "Ran 1 command, used 2 tools"},
        {"t": 59.0, "type": "row", "text": "Thought ›"},
        {"t": 59.2, "type": "say", "dur": 2.2, "text":
            "I stopped the stray script (PID 495913) and confirmed it has exited. Available memory went up from 220 MB "
            "to 375 MB, and swap use dropped from 593 MB to 549 MB.\n\n"
            "The server still uses swap because it only has 927 MB of RAM and Hermes takes about 417 MB of it. I didn't "
            "touch Hermes. If it still feels slow, adding RAM would help most."},
    ],
}

SCENES = {"push_to_prod": PUSH_TO_PROD, "free_space": FREE_SPACE, "free_memory": FREE_MEMORY}
