# LoLStat patch notes

## LoLStat 4.4.3 (2026-11-10)

Spells change the moment you pick them, and LoLStat resets when you leave a game.

- **Summoner spells:** Changing your spells in LoLStat during champ select now sets them in the client right away, even while champ select is busy. The menu shows what's set (like "Set: Flash + Mark").
- **Leaving a game:** When you leave or quit a game, LoLStat goes back to its normal pages instead of staying on that game. Your augments are still saved with the game, and if you reconnect everything comes back.

## LoLStat 4.4.2 (2026-11-10)

Privacy: LoLStat only talks to your own PC unless you turn on the phone remote.

- **Phone remote is now off by default:** LoLStat only listens on your own PC, so nothing else on your Wi-Fi can reach it. Turn on Phone remote on the Home page when you want to use your phone; it still needs the secret link in the QR code.
- **Privacy:** LoLStat doesn't collect or send anything about you. It only downloads game data, item and augment stats, and checks for updates.

## LoLStat 4.4.1 (2026-11-10)

Play is one page you scroll.

- **Play:** No more tabs: Champ select & builds, Live game and Live build are on one page. Scroll down for the live game and your Live build.

## LoLStat 4.4.0 (2026-11-10)

A cleaner sidebar, and Flash stays on your key.

- **Cleaner sidebar:** Thirteen icons became seven: Home, Play, Champions, You, Fun, Clips and Settings. Related pages sit side by side as tabs across the top: Play has Champ select & builds, Live game and Live build; You has Profile, My stats, Games & damage and Friends; Fun has Fun and Party Showdown; Settings has Settings and Help. Each group reopens on the tab you used last.
- **Live build:** Back on its own page, as a tab under Play next to Live game. It's still at the bottom of the in-game panel too.
- **Summoner spells:** Flash no longer moves to F when you keep it on D. New in Settings > Automation: Flash on D, F, or where it already is (the default). Smart picks your other spell and leaves Flash on your key.

## LoLStat 4.3.1 (2026-11-10)

Live build moved to the Live game page.

- **Live game:** Live build is no longer a page of its own: your whole build, next buy, what changed and why, and what each enemy is building now sit at the bottom of the Live game page, under scouting.

## LoLStat 4.3.0 (2026-11-10)

Live build now shows your whole build and adjusts it as the game goes, at the bottom of the in-game panel.

- **Live build in the panel:** No more switching pages: Live build sits under your builds in the in-game panel. Scroll down with the mouse wheel to reach it. The panel never gets taller than your screen.
- **Your whole build:** Live build now shows all six items, not just the next buy. It starts as the build you locked in (the same as your item set), then adjusts as the game goes: items you have are ticked, the next buy is highlighted with how much gold you need, and any item that changes is marked NEW with what it replaces and why (like "Instead of Stormrazor: armor pen vs Malphite, Ornn").
- **Live build page:** The app's Live build page shows the same full build, with what each enemy is building.

## LoLStat 4.2.2 (2026-11-09)

Item sets in the familiar layout, and other apps' item sets cleaned up.

- **Item sets:** Laid out the way you know them: Starting Items, Core Items in buy order with your boots (like Bloodthirster, Ionian Boots, Essence Reaver), then Fourth, Fifth and Sixth Item Options with up to three choices each, Situational Items and Consumables & Trinkets.
- **In-game panel:** Shows your build in the same order as the shop: Core items, then your fourth, fifth and sixth items.
- **Other apps' item sets:** Item sets left in your client by other build apps are removed automatically, so the shop only shows LoLStat's sets and your own. Sets you made yourself are never touched. Turn this off, or clean up any time, in Settings > Automation.

## LoLStat 4.2.1 (2026-11-09)

Augment cards are read no matter where LoLStat is.

- **Minimized is fine:** LoLStat keeps full speed while it's minimized or in the tray, so card grades show up instantly without keeping the app open on another screen.
- **Behind other windows:** If a window covers League (LoLStat itself, a browser, Discord), LoLStat reads the game's own picture instead of pausing. League needs to be in Borderless window mode.

## LoLStat 4.2.0 (2026-11-09)

Live build, a cleaner Settings, panel toggles and automatic updates.

- **Live build:** A new page in the in-game panel and in the app. It watches every player's items, your items, gold and augments as the game goes, and tells you what to buy next to stay ahead and do the most damage, with the reasons why (like "Malphite and Ornn are stacking armor: Lord Dominik's Regards cuts through it"). Also shows whether your items are ahead of theirs, their biggest threat and what each enemy is building. Your locked builds and item sets don't change.
- **In-game panel:** Switch between Builds and Live build at the top of the panel. Choose what else it shows in Settings: KDA, CS, CS per minute, kill participation, gold, level, your augments, start and first back, and buy now picks.
- **Settings:** Settings now has its own pages: General, Automation, In-game overlay, Clips, Look, Notifications, Party Showdown, Backup & safety, and Help & about. Search still jumps straight to any setting.
- **Automatic updates:** LoLStat checks for new versions when it opens. Click Update now and it downloads, checks and installs the update, then reopens on the new version. You can also have updates install by themselves, or check any time in Settings > General.

## LoLStat 4.1.0 (2026-11-09)

Clips: your best moments recorded automatically.

- **Clips:** Turn on clips and LoLStat records your kills, multikills, aces, objective steals and wins automatically, with game sound. Back-to-back kills become one clip, like a Triple kill.
- **Save any moment:** Press Ctrl+Shift+C in game to save the last 30 seconds.
- **Clips page:** Watch, filter and delete your clips right in the app, grouped by game. They're saved in Videos\LoLStat on your PC and nothing is uploaded.
- **Smooth while you play:** Recording uses your graphics card's video encoder, so your game stays smooth. Pick Smooth, High or Max quality, clip length, which moments to keep, and a storage limit in Settings.
- **Full games:** Optionally keep a recording of the whole game too.

## LoLStat 4.0.3 (2026-11-09)

Rebuilt augment card reading: grades show almost instantly.

- **Augment cards:** Card reading is rebuilt around the real ARAM Mayhem card screen. LoLStat spots the cards the moment they appear and reads just the card names, so grades show almost instantly, rerolls included, on any screen size or HUD scale.
- **Nothing saved:** The card captures setting is gone. LoLStat reads the cards and saves nothing.
- **License:** LoLStat is now proprietary software. You may download and use it, but copying, changing or reselling it isn't allowed.

## LoLStat 4.0.2 (2026-11-09)

Card captures, to help make augment card reading perfect.

- **Card captures:** New in Settings: Save card captures. When it's on, LoLStat saves a picture of the augment cards and what it read when cards appear, after rerolls and when a card couldn't be read. They stay on your PC in Documents\LoLStat\Card captures.
- **Ctrl+Shift+S:** In game, saves a capture any time, now in the same folder.

## LoLStat 4.0.1 (2026-11-08)

Patch notes in the app and on every release.

- **Patch notes:** Every new version now comes with patch notes: in the app after you update, under Help > Version history, and on the download page.
- **Releases:** LoLStat-Setup.exe is built, virus-scanned and published automatically for every new version.

## LoLStat 4.0.0 (2026-11-08)

Party Showdown, build guides, new item sets, faster card reading, stats and challenges.

- **Party Showdown:** Its own tab: a best of 3 or best of 5 with your party. After every game, whoever did the most damage to champions gets the point, with per-game and total damage margins.
- **Item sets:** Clear, familiar layout: Starting Items, Core Items, Boots, Fourth and Fifth Item Options, Situational Items, Consumables & Trinkets. Fixed so they show up in the in-game shop.
- **Build guide:** Every build is broken down into start, first back, core (rush the first), boots, end game and situational swaps, with BUY NOW when the enemy team calls for it.
- **In-game panel:** Shows only your builds, locked for the whole game to match your item sets. Smaller, resizable (drag the corner or Ctrl + scroll), with its own theme, see-through level, or your champion skin's colors.
- **Augment cards:** Read much faster: the moment a card is rerolled LoLStat reads just that card, and it searches harder right after level-ups.
- **Speed:** League now tells LoLStat about changes the instant they happen: instant auto-accept and champ select updates, while games stay smooth.
- **Pick up where you left off:** Opening LoLStat mid-game, or after a crash, brings back your game, augments and builds, and catches up on games played while it was closed.
- **One clean app:** Runs as a single program, closes completely when you close the window, and opens on the page you were last on.
- **My stats:** Post-game coach, records, 24 badges, an LP graph, duos and rivals, best times to play, champion journeys, highlights and a season card.
- **Fun tab:** Daily and weekly missions, a weekly Chaos mode build, your augment collection and a build lab.
- **Quality of life:** Tray icon, notifications, mini mode, Ctrl+K search, queue timer, goals, Do not disturb, custom hotkey, favorites, backups, accessibility, tilt guard, reactive themes, Help page, safe mode and clean uninstall.

## LoLStat 3.2

Champion and skin themes, automatic friends leaderboard.

## LoLStat 3.1

Player lookup, compare and shareable stats.

## LoLStat 3.0

Summoner's Rift, runes, profile, live scouting, champions.

## LoLStat 2.x

ARAM Mayhem builds, augment grades, overlay, themes.
