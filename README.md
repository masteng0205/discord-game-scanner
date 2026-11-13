# discord-game-scanner

Find PC games that **Discord can detect** — to level up the Discord profile badge
**"Game Variety"** (Sampler → Dabbler → … → Voyager → Maverick), which counts how many
*different detectable PC games* you have played with Discord open.

The scanner shows:

1. **Installed games** (Steam + Epic) and whether Discord recognises them.
2. **Games you own on Steam but have not installed** that Discord recognises, sorted with
   *never-played* games first — those are guaranteed new entries for the badge.

## Safety

- **Read-only.** It reads Discord's *public* list of detectable apps
  (`discord.com/api/v9/applications/detectable`) and local Steam/Epic library metadata.
- It **never** touches Discord's local data folder (that contains your account token) and
  never asks for a Discord token. Any tool that does is a scam.
- No third-party dependencies — Python standard library only.
- The optional Steam Web API key is read from an environment variable, never printed,
  logged or saved. Errors are sanitised so the key cannot leak into output.

## Install

Requires Python 3.13+ (Windows). With [uv](https://docs.astral.sh/uv/):

```powershell
git clone https://github.com/masteng0205/discord-game-scanner
cd discord-game-scanner
uv run discord-game-scanner
```

## Usage

```powershell
uv run discord-game-scanner                     # installed games
uv run discord-game-scanner --html report.html  # + HTML report
```

### Owned-but-not-installed games (Steam)

1. Create a key at <https://steamcommunity.com/dev/apikey> (domain: `localhost`).
2. Put it in an environment variable for the current terminal only — paste it at the
   prompt, never into chats, screenshots or files:
   ```powershell
   $env:STEAM_API_KEY = Read-Host "Paste your Steam API key"
   ```
3. Run with your SteamID64 (find it at <https://steamid.io>):
   ```powershell
   uv run discord-game-scanner --owned --steamid 7656119XXXXXXXXXX --html report.html
   ```
4. **Revoke the key** afterwards on the same Steam page. The game list is cached locally
   (`%LOCALAPPDATA%\discord-game-scanner`), so later runs with `--owned` work without a key.

Your Steam profile's *Game details* privacy must allow the API to see your library.

### Hide games Discord already counted

Discord has no API for which games it already counted. Copy the names from
**Discord → User Settings → Registered Games** into a text file (one per line) and run:

```powershell
uv run discord-game-scanner --owned --exclude-file exclude.txt
```

## Limitations

- Status labels come from Steam playtime, because Discord does not expose which games it
  already counted:
  - **NEVER PLAYED** — 0 minutes on Steam, so Discord cannot have counted it yet.
  - **played on Steam - unknown on Discord** — Steam saw you play it, but Discord only counts
    a game if the Discord desktop app was running and detected it at the time. It may be
    missing if Discord was closed, activity detection was off, you played on another device,
    it was before Discord started tracking, or the game was not yet on Discord's list.
    Playing it again for a few minutes with Discord open makes sure it counts.
- Only Steam and Epic libraries are scanned for installed games.
- Discord's detection list and badge rules can change at any time.

## Development

```powershell
uv run python -m unittest discover -s tests -v
```

Not affiliated with Discord or Valve.

## License

MIT
