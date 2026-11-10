"""LoLStat patch notes: the one place they're written.

Shown in the app (What's new after an update, and Help > Version history), published as the
GitHub release notes for each version, and written to CHANGELOG.md.

Every change: add an entry at the TOP for the new version, then run
    python tools/bump_version.py <new version>
and push to main. GitHub builds, scans and releases it. The build refuses a version with no notes here.
"""
import sys

# newest first. "changes" are (heading, what changed) pairs, written for players.
NOTES = [
    {
        "version": "4.3.1",
        "date": "2026-11-10",
        "summary": "Live build moved to the Live game page.",
        "changes": [
            ("Live game", "Live build is no longer a page of its own: your whole build, next buy, what changed and why, and what each enemy is building now sit at the bottom of the Live game page, under scouting."),
        ],
    },
    {
        "version": "4.3.0",
        "date": "2026-11-10",
        "summary": "Live build now shows your whole build and adjusts it as the game goes, at the bottom of the in-game panel.",
        "changes": [
            ("Live build in the panel", "No more switching pages: Live build sits under your builds in the in-game panel. Scroll down with the mouse wheel to reach it. The panel never gets taller than your screen."),
            ("Your whole build", "Live build now shows all six items, not just the next buy. It starts as the build you locked in (the same as your item set), then adjusts as the game goes: items you have are ticked, the next buy is highlighted with how much gold you need, and any item that changes is marked NEW with what it replaces and why (like \"Instead of Stormrazor: armor pen vs Malphite, Ornn\")."),
            ("Live build page", "The app's Live build page shows the same full build, with what each enemy is building."),
        ],
    },
    {
        "version": "4.2.2",
        "date": "2026-11-09",
        "summary": "Item sets in the familiar layout, and other apps' item sets cleaned up.",
        "changes": [
            ("Item sets", "Laid out the way you know them: Starting Items, Core Items in buy order with your boots (like Bloodthirster, Ionian Boots, Essence Reaver), then Fourth, Fifth and Sixth Item Options with up to three choices each, Situational Items and Consumables & Trinkets."),
            ("In-game panel", "Shows your build in the same order as the shop: Core items, then your fourth, fifth and sixth items."),
            ("Other apps' item sets", "Item sets left in your client by other build apps are removed automatically, so the shop only shows LoLStat's sets and your own. Sets you made yourself are never touched. Turn this off, or clean up any time, in Settings > Automation."),
        ],
    },
    {
        "version": "4.2.1",
        "date": "2026-11-09",
        "summary": "Augment cards are read no matter where LoLStat is.",
        "changes": [
            ("Minimized is fine", "LoLStat keeps full speed while it's minimized or in the tray, so card grades show up instantly without keeping the app open on another screen."),
            ("Behind other windows", "If a window covers League (LoLStat itself, a browser, Discord), LoLStat reads the game's own picture instead of pausing. League needs to be in Borderless window mode."),
        ],
    },
    {
        "version": "4.2.0",
        "date": "2026-11-09",
        "summary": "Live build, a cleaner Settings, panel toggles and automatic updates.",
        "changes": [
            ("Live build", "A new page in the in-game panel and in the app. It watches every player's items, your items, gold and augments as the game goes, and tells you what to buy next to stay ahead and do the most damage, with the reasons why (like \"Malphite and Ornn are stacking armor: Lord Dominik's Regards cuts through it\"). Also shows whether your items are ahead of theirs, their biggest threat and what each enemy is building. Your locked builds and item sets don't change."),
            ("In-game panel", "Switch between Builds and Live build at the top of the panel. Choose what else it shows in Settings: KDA, CS, CS per minute, kill participation, gold, level, your augments, start and first back, and buy now picks."),
            ("Settings", "Settings now has its own pages: General, Automation, In-game overlay, Clips, Look, Notifications, Party Showdown, Backup & safety, and Help & about. Search still jumps straight to any setting."),
            ("Automatic updates", "LoLStat checks for new versions when it opens. Click Update now and it downloads, checks and installs the update, then reopens on the new version. You can also have updates install by themselves, or check any time in Settings > General."),
        ],
    },
    {
        "version": "4.1.0",
        "date": "2026-11-09",
        "summary": "Clips: your best moments recorded automatically.",
        "changes": [
            ("Clips", "Turn on clips and LoLStat records your kills, multikills, aces, objective steals and wins automatically, with game sound. Back-to-back kills become one clip, like a Triple kill."),
            ("Save any moment", "Press Ctrl+Shift+C in game to save the last 30 seconds."),
            ("Clips page", "Watch, filter and delete your clips right in the app, grouped by game. They're saved in Videos\\LoLStat on your PC and nothing is uploaded."),
            ("Smooth while you play", "Recording uses your graphics card's video encoder, so your game stays smooth. Pick Smooth, High or Max quality, clip length, which moments to keep, and a storage limit in Settings."),
            ("Full games", "Optionally keep a recording of the whole game too."),
        ],
    },
    {
        "version": "4.0.3",
        "date": "2026-11-09",
        "summary": "Rebuilt augment card reading: grades show almost instantly.",
        "changes": [
            ("Augment cards", "Card reading is rebuilt around the real ARAM Mayhem card screen. LoLStat spots the cards the moment they appear and reads just the card names, so grades show almost instantly, rerolls included, on any screen size or HUD scale."),
            ("Nothing saved", "The card captures setting is gone. LoLStat reads the cards and saves nothing."),
            ("License", "LoLStat is now proprietary software. You may download and use it, but copying, changing or reselling it isn't allowed."),
        ],
    },
    {
        "version": "4.0.2",
        "date": "2026-11-09",
        "summary": "Card captures, to help make augment card reading perfect.",
        "changes": [
            ("Card captures", "New in Settings: Save card captures. When it's on, LoLStat saves a picture of the augment cards and what it read when cards appear, after rerolls and when a card couldn't be read. They stay on your PC in Documents\\LoLStat\\Card captures."),
            ("Ctrl+Shift+S", "In game, saves a capture any time, now in the same folder."),
        ],
    },
    {
        "version": "4.0.1",
        "date": "2026-11-08",
        "summary": "Patch notes in the app and on every release.",
        "changes": [
            ("Patch notes", "Every new version now comes with patch notes: in the app after you update, under Help > Version history, and on the download page."),
            ("Releases", "LoLStat-Setup.exe is built, virus-scanned and published automatically for every new version."),
        ],
    },
    {
        "version": "4.0.0",
        "date": "2026-11-08",
        "summary": "Party Showdown, build guides, new item sets, faster card reading, stats and challenges.",
        "changes": [
            ("Party Showdown", "Its own tab: a best of 3 or best of 5 with your party. After every game, whoever did the most damage to champions gets the point, with per-game and total damage margins."),
            ("Item sets", "Clear, familiar layout: Starting Items, Core Items, Boots, Fourth and Fifth Item Options, Situational Items, Consumables & Trinkets. Fixed so they show up in the in-game shop."),
            ("Build guide", "Every build is broken down into start, first back, core (rush the first), boots, end game and situational swaps, with BUY NOW when the enemy team calls for it."),
            ("In-game panel", "Shows only your builds, locked for the whole game to match your item sets. Smaller, resizable (drag the corner or Ctrl + scroll), with its own theme, see-through level, or your champion skin's colors."),
            ("Augment cards", "Read much faster: the moment a card is rerolled LoLStat reads just that card, and it searches harder right after level-ups."),
            ("Speed", "League now tells LoLStat about changes the instant they happen: instant auto-accept and champ select updates, while games stay smooth."),
            ("Pick up where you left off", "Opening LoLStat mid-game, or after a crash, brings back your game, augments and builds, and catches up on games played while it was closed."),
            ("One clean app", "Runs as a single program, closes completely when you close the window, and opens on the page you were last on."),
            ("My stats", "Post-game coach, records, 24 badges, an LP graph, duos and rivals, best times to play, champion journeys, highlights and a season card."),
            ("Fun tab", "Daily and weekly missions, a weekly Chaos mode build, your augment collection and a build lab."),
            ("Quality of life", "Tray icon, notifications, mini mode, Ctrl+K search, queue timer, goals, Do not disturb, custom hotkey, favorites, backups, accessibility, tilt guard, reactive themes, Help page, safe mode and clean uninstall."),
        ],
    },
    {"version": "3.2", "date": "", "summary": "Champion and skin themes, automatic friends leaderboard.", "changes": []},
    {"version": "3.1", "date": "", "summary": "Player lookup, compare and shareable stats.", "changes": []},
    {"version": "3.0", "date": "", "summary": "Summoner's Rift, runes, profile, live scouting, champions.", "changes": []},
    {"version": "2.x", "date": "", "summary": "ARAM Mayhem builds, augment grades, overlay, themes.", "changes": []},
]


def entry(version):
    return next((n for n in NOTES if n["version"] == version), None)


def latest():
    return NOTES[0]


def markdown(version):
    n = entry(version)
    if not n:
        return None
    lines = [f"## LoLStat {n['version']}" + (f" ({n['date']})" if n["date"] else ""), "", n["summary"], ""]
    lines += [f"- **{h}:** {t}" for h, t in n["changes"]]
    return "\n".join(lines).rstrip() + "\n"


def changelog():
    return "# LoLStat patch notes\n\n" + "\n".join(markdown(n["version"]) for n in NOTES)


if __name__ == "__main__":
    # python patch_notes.py <version>  -> that version's notes (used for the GitHub release)
    # python patch_notes.py --all       -> the whole changelog
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        print(changelog())
    else:
        v = sys.argv[1] if len(sys.argv) > 1 else latest()["version"]
        md = markdown(v)
        if not md:
            sys.exit(f"No patch notes for {v}: add them to patch_notes.py")
        print(md)
