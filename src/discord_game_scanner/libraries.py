"""Discover installed games from Steam and Epic Games Launcher (read-only)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import vdf


@dataclass
class InstalledGame:
    store: str  # "steam" | "epic"
    store_id: str
    name: str
    install_dir: Path
    extra_ids: tuple[str, ...] = ()
    last_played: int | None = None  # unix time, Steam only
    playtime_min: int | None = None  # Steam only


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------- Steam

def steam_root() -> Path | None:
    if os.name == "nt":
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for value in ("SteamPath", "InstallPath"):
                        try:
                            p = Path(winreg.QueryValueEx(k, value)[0])
                            if p.exists():
                                return p
                        except OSError:
                            pass
            except OSError:
                pass
    for guess in (Path(r"C:\Program Files (x86)\Steam"), Path.home() / ".steam/steam"):
        if guess.exists():
            return guess
    return None


def steam_libraries(root: Path) -> list[Path]:
    libs = [root]
    text = _read(root / "steamapps" / "libraryfolders.vdf")
    if text:
        folders = vdf.get_ci(vdf.loads(text), "libraryfolders") or {}
        for entry in folders.values():
            path = entry.get("path") if isinstance(entry, dict) else entry
            if path:
                p = Path(path)
                if p.exists() and all(p.resolve() != q.resolve() for q in libs):
                    libs.append(p)
    return libs


def steam_playtime(root: Path) -> dict[str, tuple[int, int]]:
    """appid -> (last_played, playtime_minutes), merged over all local Steam users.

    Only the per-app play statistics are extracted from localconfig.vdf.
    """
    result: dict[str, tuple[int, int]] = {}
    userdata = root / "userdata"
    if not userdata.is_dir():
        return result
    for user in userdata.iterdir():
        text = _read(user / "config" / "localconfig.vdf")
        if not text:
            continue
        apps = vdf.get_ci(vdf.loads(text), "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or {}
        for appid, info in apps.items():
            if not isinstance(info, dict):
                continue
            lp = int(vdf.get_ci(info, "LastPlayed") or 0)
            pt = int(vdf.get_ci(info, "Playtime") or 0)
            old = result.get(appid, (0, 0))
            result[appid] = (max(old[0], lp), max(old[1], pt))
    return result


def steam_games() -> list[InstalledGame]:
    root = steam_root()
    if not root:
        return []
    stats = steam_playtime(root)
    games = []
    for lib in steam_libraries(root):
        steamapps = lib / "steamapps"
        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            text = _read(manifest)
            if not text:
                continue
            state = vdf.get_ci(vdf.loads(text), "AppState") or {}
            appid, name, installdir = state.get("appid"), state.get("name"), state.get("installdir")
            if not (appid and installdir):
                continue
            lp, pt = stats.get(appid, (0, 0))
            games.append(InstalledGame(
                store="steam", store_id=appid, name=name or installdir,
                install_dir=steamapps / "common" / installdir,
                last_played=lp or None, playtime_min=pt or None,
            ))
    return games


# ---------------------------------------------------------------- Epic

def epic_manifest_dir() -> Path | None:
    candidates = []
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher") as k:
                candidates.append(Path(winreg.QueryValueEx(k, "AppDataPath")[0]) / "Manifests")
        except OSError:
            pass
    candidates.append(Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"))
    return next((c for c in candidates if c.is_dir()), None)


def epic_games() -> list[InstalledGame]:
    mdir = epic_manifest_dir()
    if not mdir:
        return []
    games = []
    for item in sorted(mdir.glob("*.item")):
        try:
            data = json.loads(_read(item) or "")
        except ValueError:
            continue
        if not data.get("bIsApplication", True) or data.get("bIsIncompleteInstall"):
            continue
        loc = data.get("InstallLocation")
        if not loc:
            continue
        ids = tuple(str(x) for x in (data.get("CatalogItemId"), data.get("MainGameAppName"), data.get("CatalogNamespace")) if x)
        games.append(InstalledGame(
            store="epic", store_id=str(data.get("AppName", "")),
            name=data.get("DisplayName") or data.get("AppName", "?"),
            install_dir=Path(loc), extra_ids=ids,
        ))
    return games


def all_games() -> list[InstalledGame]:
    return steam_games() + epic_games()
