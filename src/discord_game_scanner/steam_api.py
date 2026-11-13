"""Steam Web API: list every game the user owns (installed or not).

The API key is read from the STEAM_API_KEY environment variable and is never
printed, logged or written to disk.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

OWNED_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
USER_AGENT = "discord-game-scanner/0.1"
STEAMID64_RE = re.compile(r"^7656119\d{10}$")


class SteamApiError(RuntimeError):
    pass


@dataclass
class OwnedGame:
    appid: str
    name: str
    playtime_min: int
    last_played: int | None


def get_owned_games(steamid: str, api_key: str | None = None, timeout: float = 30.0) -> list[OwnedGame]:
    api_key = api_key or os.environ.get("STEAM_API_KEY")
    if not api_key:
        raise SteamApiError("STEAM_API_KEY environment variable is not set.")
    if not STEAMID64_RE.match(steamid):
        raise SteamApiError(f"'{steamid}' is not a SteamID64 (17 digits starting with 7656119).")

    query = urllib.parse.urlencode({
        "key": api_key, "steamid": steamid, "format": "json",
        "include_appinfo": 1, "include_played_free_games": 1,
    })
    req = urllib.request.Request(f"{OWNED_URL}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Never include the request URL in errors: it contains the key.
        hint = " (invalid API key?)" if e.code in (401, 403) else ""
        raise SteamApiError(f"Steam API returned HTTP {e.code}{hint}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SteamApiError(f"Could not reach Steam API: {getattr(e, 'reason', e)}") from None

    games = (data.get("response") or {}).get("games")
    if games is None:
        raise SteamApiError(
            "Steam returned no games. Set Steam profile > Privacy > 'Game details' to Public "
            "(or 'Friends only' may not be enough), then try again."
        )
    return [
        OwnedGame(
            appid=str(g["appid"]),
            name=g.get("name") or f"app {g['appid']}",
            playtime_min=int(g.get("playtime_forever") or 0),
            last_played=int(g.get("rtime_last_played") or 0) or None,
        )
        for g in games
    ]


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Loose name key for comparing titles across Steam and Discord ("HELLDIVERS™ 2" == "helldivers 2")."""
    return _NORMALIZE_RE.sub("", name.lower())
