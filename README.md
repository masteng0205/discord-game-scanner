# discord-game-scanner

Find PC games that **Discord can detect**, to level up the Discord profile badge
**"Game Variety"** (Sampler → Dabbler → Enthusiast → Ranger → Explorer → Adventurer →
Voyager → Maverick → …). The badge counts how many *different detectable PC games* you have
played **while the Discord desktop app was running**.

The scanner shows:

1. **Installed games** (Steam + Epic) and whether Discord recognises them.
2. **Games you own on Steam but have not installed** that Discord recognises, with
   *never-played* games first — those are guaranteed new entries for the badge.

```text
▶ NEVER PLAYED — certainly not counted by Discord yet (31)
Game                          Playtime  Last played
----------------------------  --------  -----------
Portal 2                      0         -
Outlast 2                     0         -
  ... and 29 more (use --limit 0 to show all, or open the HTML report)

▶ Played on Steam — unknown on Discord (139) — oldest first
Game                          Playtime  Last played
----------------------------  --------  -----------
Left 4 Dead 2                 3.1 h     2016-04-06
...

=== Next step ===
31 games you own were never played: Portal 2, Outlast 2, ...
Install any of them and play a few minutes with Discord open to grow the badge.
```

The optional HTML report has one-click **Install** links that open Steam.

## Is it safe?

- **Read-only.** It only reads Discord's *public* list of detectable games
  (`discord.com/api/v9/applications/detectable`) and your local Steam/Epic library files.
- It **never** touches Discord's own data folder (which contains your login token) and
  **never asks for a Discord token or password**. Any tool that does is a scam.
- No third-party dependencies: Python standard library only. The source is ~800 lines in
  [`src/`](src/discord_game_scanner) — feel free to read it.
- The optional Steam Web API key is only read from an environment variable; it is never
  printed, logged or saved, and errors are sanitised so it cannot leak.

## Quick start (Windows)

**1. Open PowerShell** — press `Win + X` and choose *Terminal* (or *Windows PowerShell*).

**2. Install [uv](https://docs.astral.sh/uv/) once** (a small, official Python tool runner; it
also downloads Python for you if needed):

```powershell
winget install --id astral-sh.uv -e
```

Close and reopen PowerShell after installing.

**3. Run the scanner** straight from GitHub — no git, no manual Python install:

```powershell
uvx --from https://github.com/masteng0205/discord-game-scanner/archive/refs/heads/main.zip discord-game-scanner --html report.html
```

Open the report with `start report.html`.

> Tip: to type less next time, create a short alias for the current PowerShell session:
> ```powershell
> function dgs { uvx --from https://github.com/masteng0205/discord-game-scanner/archive/refs/heads/main.zip discord-game-scanner @args }
> dgs --html report.html
> ```
> The examples below use `dgs`; replace it with the full `uvx ...` command if you skipped this.

## See games you own but have not installed (Steam)

This needs a free Steam Web API key **once**; afterwards the list is cached on your PC.

1. **Find your SteamID64** (17 digits starting with `7656119…`): open your Steam profile in a
   browser — it is in the URL `steamcommunity.com/profiles/7656119…`, or look it up at
   <https://steamid.io>.
2. **Make your game list visible to the API:** Steam → your profile → *Edit Profile* →
   *Privacy Settings* → **Game details: Public**. (You can switch it back afterwards.)
3. **Create a key** at <https://steamcommunity.com/dev/apikey> — *Domain Name* can be
   `localhost`.
4. **Paste the key into the current terminal only** (never into chats, screenshots or files):
   ```powershell
   $env:STEAM_API_KEY = Read-Host "Paste your Steam API key"
   ```
5. **Run:**
   ```powershell
   dgs --owned --steamid 7656119XXXXXXXXXX --html report.html
   ```
6. **Revoke the key** on the same Steam page when you are done. Later runs with `--owned`
   reuse the cached list (`%LOCALAPPDATA%\discord-game-scanner`) and need no key.

Save your SteamID so you don't have to type it each time (it is not a secret):

```powershell
[Environment]::SetEnvironmentVariable("STEAM_ID", "7656119XXXXXXXXXX", "User")
```

Reopen PowerShell, then simply run `dgs --owned`.

### Useful options

| Option | What it does |
|---|---|
| `--never-only` | Only show games you have never played (best candidates) |
| `--limit N` | Rows per section in the terminal (default 15, `0` = all) |
| `--html FILE` | Write an HTML report with Steam install links |
| `--json FILE` | Write a machine-readable JSON report |
| `--exclude-file FILE` | Hide games listed in a text file (see below) |
| `--refresh` | Re-download Discord's game list (cached for 24 h) |

### Hide games Discord already counted

Discord has no public API for which games it already counted. Copy the names from
**Discord → User Settings → Registered Games** into a text file, one per line, and run:

```powershell
dgs --owned --exclude-file exclude.txt
```

## Understanding the results

Discord does not expose which games your badge already includes, so the labels are based
on Steam playtime:

- **NEVER PLAYED** — 0 minutes on Steam, so Discord cannot have counted it yet.
  Install it and play a few minutes with Discord open.
- **Played on Steam — unknown on Discord** — Steam saw you play it, but Discord only counts
  a game if the Discord desktop app was running and detected it *at that time*. It may be
  missing if Discord was closed, *Activity Privacy → Share your detected activities* was off,
  you played on another device, it was before Discord started tracking, or the game was not
  yet on Discord's list. Playing it again briefly with Discord open makes sure it counts.

To make sure a session counts: keep the **Discord desktop app** running and check that your
status shows **"Playing …"** while the game is open. The badge may take a while to update.

## Troubleshooting

| Message | Fix |
|---|---|
| `uvx` / `uv` is not recognized | Close and reopen PowerShell after installing uv. |
| `No installed Steam or Epic games found` | Only Steam and Epic Games Launcher libraries are scanned. |
| `Steam API returned HTTP 401/403 (invalid API key?)` | Check the key (or create a new one); make sure it is set in *this* terminal. |
| `Steam returned no games` | Set Steam *Privacy Settings → Game details* to **Public**. |
| `--owned needs your SteamID64` | Add `--steamid 7656119…` or set the `STEAM_ID` variable. |
| Strange characters in the table | Use Windows Terminal, or run `chcp 65001` first. |

## Limitations

- Windows only for installed-game detection (Steam + Epic). The `--owned` list works anywhere.
- Discord's detection list and badge rules can change at any time.

## Development

```powershell
git clone https://github.com/masteng0205/discord-game-scanner
cd discord-game-scanner
uv run discord-game-scanner
uv run python -m unittest discover -s tests -v
```

Not affiliated with Discord or Valve.

## License

[MIT](LICENSE)
