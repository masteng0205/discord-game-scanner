"""Command-line entry point."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__
from .detectable import DetectableIndex, cache_dir, load_detectable
from .libraries import all_games
from .scanner import ScanResult, scan
from .steam_api import OwnedGame, SteamApiError, get_owned_games, normalize_name

NEVER = "NEVER PLAYED -> surely not counted"
MAYBE = "played on Steam - unknown on Discord"


def _fmt_date(ts: int | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "-"


def _status(r: ScanResult) -> str:
    if not r.detectable:
        return "not detectable"
    if r.game.store == "steam" and not r.game.last_played:
        return "NEVER PLAYED -> candidate"
    return "played on Steam - unknown on Discord" if r.game.last_played else "unknown (not Steam)"


def _sort_key(r: ScanResult):
    order = {"NEVER PLAYED -> candidate": 0, "unknown (not Steam)": 1, "played on Steam - unknown on Discord": 2, "not detectable": 3}
    return (order[_status(r)], r.game.name.lower())


def _print_rows(rows: list[tuple[str, ...]], max_w: int = 45) -> None:
    widths = [min(max(len(r[i]) for r in rows), max_w) for i in range(len(rows[0]))]
    for n, row in enumerate(rows):
        print("  ".join(c[:max_w].ljust(w) for c, w in zip(row, widths)))
        if n == 0:
            print("  ".join("-" * w for w in widths))


# ------------------------------------------------------------ installed games

def print_installed(results: list[ScanResult]) -> None:
    rows = [("Game", "Store", "Discord detects as", "Via", "Last played", "Status")]
    for r in sorted(results, key=_sort_key):
        rows.append((r.game.name, r.game.store, r.discord_app["name"] if r.discord_app else "-",
                     r.method or "-", _fmt_date(r.game.last_played), _status(r)))
    _print_rows(rows, 40)


# ------------------------------------------------------------ owned (Steam API)

def _owned_cache(steamid: str) -> Path:
    return cache_dir() / f"owned-{steamid}.json"


def load_owned(steamid: str) -> tuple[list[OwnedGame], str]:
    """Fetch owned games via the API (needs STEAM_API_KEY); fall back to the last cached result.

    The cache stores only the public game list (appid, name, playtime) — never the API key.
    """
    cache = _owned_cache(steamid)
    api_error = None
    if os.environ.get("STEAM_API_KEY"):
        try:
            owned = get_owned_games(steamid)
        except SteamApiError as e:
            if not cache.exists():
                raise
            api_error = e
        else:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([asdict(g) for g in owned]), encoding="utf-8")
            return owned, "Steam Web API (live)"
    if cache.exists():
        if api_error:
            print(f"\nSteam API failed ({api_error}); falling back to the cached list.")
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        owned = [OwnedGame(**g) for g in json.loads(cache.read_text(encoding="utf-8"))]
        return owned, f"cached list from {age_days:.0f} day(s) ago (set STEAM_API_KEY to refresh)"
    raise SteamApiError("STEAM_API_KEY is not set and no cached owned-games list exists yet.")


def _load_excludes(path: Path | None) -> set[str]:
    if not path:
        return set()
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return {normalize_name(l) for l in lines if l.strip() and not l.lstrip().startswith("#")}


def owned_candidates(owned: list[OwnedGame], index: DetectableIndex,
                     installed_ids: set[str], excludes: set[str]) -> list[tuple[OwnedGame, dict]]:
    rows = []
    for g in owned:
        if g.appid in installed_ids:
            continue
        app = index.match_sku("steam", g.appid)
        if not app or normalize_name(g.name) in excludes or normalize_name(app["name"]) in excludes:
            continue
        rows.append((g, app))
    # never played first, then least recently played
    rows.sort(key=lambda ga: (ga[0].playtime_min > 0, ga[0].last_played or 0, ga[0].name.lower()))
    return rows


def _hint(g: OwnedGame) -> str:
    return NEVER if g.playtime_min == 0 else MAYBE


def _fmt_playtime(minutes: int) -> str:
    if minutes == 0:
        return "0"
    if minutes < 6:  # would round to 0.0 h and look like "never played"
        return "<0.1 h"
    return f"{minutes / 60:.1f} h"


def _print_section(title: str, rows: list[tuple[OwnedGame, dict]], limit: int, note: str = "") -> None:
    print(f"\n▶ {title} ({len(rows)})" + (f" — {note}" if note else ""))
    if not rows:
        print("  (none)")
        return
    shown = rows if limit <= 0 else rows[:limit]
    table = [("Game", "Playtime", "Last played")]
    table += [(g.name, _fmt_playtime(g.playtime_min), _fmt_date(g.last_played)) for g, _ in shown]
    _print_rows(table)
    if len(shown) < len(rows):
        print(f"  ... and {len(rows) - len(shown)} more (use --limit 0 to show all, or open the HTML report)")


def print_owned(rows: list[tuple[OwnedGame, dict]], total_owned: int, source: str,
                limit: int = 15, never_only: bool = False) -> list[OwnedGame]:
    """Print owned-but-not-installed games in two sections; return the never-played ones."""
    never = [(g, a) for g, a in rows if g.playtime_min == 0]
    played = [(g, a) for g, a in rows if g.playtime_min > 0]
    print(f"\n=== Owned on Steam, NOT installed, detectable by Discord ({len(rows)} of {total_owned} owned) ===")
    print(f"Source: {source}")
    _print_section("NEVER PLAYED — certainly not counted by Discord yet", never, limit)
    if not never_only:
        _print_section("Played on Steam — unknown on Discord", played, limit,
                       note="oldest first; older games are more likely to be missing")
    return [g for g, _ in never]


def print_next_steps(never: list[OwnedGame], html_path: Path | None, show: int = 10) -> None:
    print("\n=== Next step ===")
    if never:
        names = ", ".join(g.name for g in never[:show])
        more = f" (+{len(never) - show} more)" if len(never) > show else ""
        print(f"{len(never)} games you own were never played: {names}{more}.")
        print("Install any of them and play a few minutes with Discord open to grow the badge.")
    else:
        print("No never-played games left; replay older games with Discord open.")
    if html_path:
        print(f"Install links: open {html_path.resolve()}")
    else:
        print("Tip: add --html report.html for a report with one-click Steam install links.")


# ------------------------------------------------------------ reports

def write_html(results: list[ScanResult], owned_rows: list[tuple[OwnedGame, dict]] | None, path: Path) -> None:
    e = html.escape
    inst = "".join(
        f"<tr class='{'cand' if _status(r).startswith('NEVER') else ''}'>"
        f"<td>{e(r.game.name)}</td><td>{e(r.game.store)}</td>"
        f"<td>{e(r.discord_app['name']) if r.discord_app else '-'}</td>"
        f"<td>{e(r.method or '-')}</td><td>{_fmt_date(r.game.last_played)}</td>"
        f"<td>{e(_status(r))}</td></tr>"
        for r in sorted(results, key=_sort_key)
    )
    owned_html = ""
    if owned_rows is not None:
        body = "".join(
            f"<tr class='{'cand' if g.playtime_min == 0 else ''}'><td>{e(g.name)}</td>"
            f"<td>{e(_fmt_playtime(g.playtime_min))}</td><td>{_fmt_date(g.last_played)}</td><td>{e(_hint(g))}</td>"
            f"<td><a href='steam://install/{e(g.appid)}'>install</a></td></tr>"
            for g, _ in owned_rows
        )
        owned_html = ("<h2>Owned on Steam, not installed, detectable by Discord</h2>"
                      "<table><tr><th>Game</th><th>Playtime</th><th>Last played</th><th>Hint</th><th></th></tr>"
                      f"{body}</table>")
    path.write_text(
        "<!doctype html><meta charset='utf-8'><title>Discord Game Scanner</title>"
        "<style>body{font:14px system-ui;margin:24px;background:#1e1f22;color:#dbdee1}"
        "table{border-collapse:collapse;width:100%;margin-bottom:32px}"
        "td,th{padding:6px 10px;border-bottom:1px solid #3f4147;text-align:left}"
        "th{color:#949ba4}tr.cand td{color:#57f287;font-weight:600}a{color:#00a8fc}</style>"
        f"<h1>Discord Game Scanner</h1><p>Generated {datetime.now():%Y-%m-%d %H:%M}</p>"
        "<h2>Installed games</h2><table><tr><th>Game</th><th>Store</th><th>Discord detects as</th>"
        f"<th>Via</th><th>Last played</th><th>Status</th></tr>{inst}</table>{owned_html}",
        encoding="utf-8",
    )


def write_json(results: list[ScanResult], owned_rows, path: Path) -> None:
    data = {
        "installed": [
            {"name": r.game.name, "store": r.game.store, "store_id": r.game.store_id,
             "install_dir": str(r.game.install_dir), "detectable": r.detectable,
             "discord_name": r.discord_app["name"] if r.discord_app else None,
             "discord_app_id": r.discord_app["id"] if r.discord_app else None,
             "method": r.method, "matched_exe": r.matched_exe,
             "last_played": r.game.last_played, "status": _status(r)}
            for r in results],
        "owned_not_installed": None if owned_rows is None else [
            {"appid": g.appid, "name": g.name, "discord_name": app["name"], "discord_app_id": app["id"],
             "playtime_min": g.playtime_min, "last_played": g.last_played, "hint": _hint(g)}
            for g, app in owned_rows],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------ main

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="discord-game-scanner",
        description="List installed Steam/Epic games and whether Discord can detect them "
                    "(useful for the Discord 'Game Variety' badge).",
    )
    p.add_argument("--refresh", action="store_true", help="re-download Discord's detectable list (cached 24h)")
    p.add_argument("--html", type=Path, metavar="FILE", help="also write an HTML report")
    p.add_argument("--json", type=Path, metavar="FILE", help="also write a JSON report")
    p.add_argument("--owned", action="store_true",
                   help="also list games you OWN on Steam but have not installed "
                        "(needs STEAM_API_KEY; afterwards a cached list is reused)")
    p.add_argument("--steamid", default=os.environ.get("STEAM_ID"),
                   help="your SteamID64 (or set STEAM_ID env var)")
    p.add_argument("--exclude-file", type=Path, metavar="FILE",
                   help="text file with game names already counted by Discord (one per line, "
                        "e.g. copied from Settings > Registered Games); they are hidden")
    p.add_argument("--never-only", action="store_true",
                   help="with --owned: only show games you have never played (best badge candidates)")
    p.add_argument("--limit", type=int, default=15, metavar="N",
                   help="max rows per owned-games section in the terminal (default 15, 0 = all); "
                        "reports always contain everything")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    if args.never_only:
        args.owned = True

    print("Loading Discord's detectable application list...")
    index = DetectableIndex.build(load_detectable(refresh=args.refresh))
    games = all_games()
    print(f"{index.total:,} detectable apps known to Discord; {len(games)} installed games found.\n")

    results = scan(games, index)
    if results:
        print_installed(results)
        det = [r for r in results if r.detectable]
        cand = [r for r in det if _status(r).startswith("NEVER")]
        print(f"\nDetectable by Discord: {len(det)}/{len(results)}   Never played (Steam): {len(cand)}")
    else:
        print("No installed Steam or Epic games found.")
    print("Note: Discord does not expose which games your account has already counted.\n"
          "Compare with Discord > User Settings > Registered Games.")

    owned_rows = None
    if args.owned:
        if not args.steamid:
            print("\n--owned needs your SteamID64: pass --steamid or set the STEAM_ID env var.")
            return 2
        try:
            owned, source = load_owned(args.steamid)
        except SteamApiError as e:
            print(f"\nSteam API error: {e}")
            return 2
        installed_ids = {r.game.store_id for r in results if r.game.store == "steam"}
        owned_rows = owned_candidates(owned, index, installed_ids, _load_excludes(args.exclude_file))
        never = print_owned(owned_rows, len(owned), source, limit=args.limit, never_only=args.never_only)

    if args.html:
        write_html(results, owned_rows, args.html)
        print(f"\nHTML report: {args.html.resolve()}")
    if args.json:
        write_json(results, owned_rows, args.json)
        print(f"JSON report: {args.json.resolve()}")
    if owned_rows is not None:
        print_next_steps(never, args.html)  # last, so it is what the user sees first
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
