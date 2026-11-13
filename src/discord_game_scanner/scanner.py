"""Match installed games against Discord's detectable list."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .detectable import DetectableIndex
from .libraries import InstalledGame

MAX_DEPTH = 6
SKIP_DIRS = {"__installer", "_commonredist", "commonredist", "redist", "directx", "vcredist", "support", "easyanticheat_eos_setup"}


@dataclass
class ScanResult:
    game: InstalledGame
    discord_app: dict | None
    method: str | None  # "sku", "exe" or None
    matched_exe: str | None = None

    @property
    def detectable(self) -> bool:
        return self.discord_app is not None


def iter_exes(root: Path, max_depth: int = MAX_DEPTH):
    """Yield lower-case relative path parts of every .exe below root."""
    if not root.is_dir():
        return
    root_s = str(root)
    base_depth = root_s.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root_s):
        depth = dirpath.count(os.sep) - base_depth
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS] if depth < max_depth else []
        for f in filenames:
            if f.lower().endswith(".exe"):
                rel = os.path.relpath(os.path.join(dirpath, f), root_s)
                # include the install folder name itself so patterns like
                # "garrysmod/hl2.exe" or "tom clancy's .../x.exe" can match
                yield tuple(p.lower() for p in Path(root.name, rel).parts)


def scan_game(game: InstalledGame, index: DetectableIndex) -> ScanResult:
    # 1) Store ID listed by Discord itself: most reliable.
    sku_ids = (game.store_id, *game.extra_ids)
    sku_app = next((a for s in sku_ids if s and (a := index.match_sku(game.store, s))), None)

    # 2) Executable path match (what Discord's process detection uses).
    exe_hit = None
    for rel in iter_exes(game.install_dir):
        app = index.match_exe(rel)
        if app and (sku_app is None or app is sku_app):
            exe_hit = (app, "/".join(rel[1:]))
            break

    if sku_app:
        return ScanResult(game, sku_app, "sku", exe_hit[1] if exe_hit else None)
    if exe_hit:
        return ScanResult(game, exe_hit[0], "exe", exe_hit[1])
    return ScanResult(game, None, None)


def scan(games: list[InstalledGame], index: DetectableIndex) -> list[ScanResult]:
    return [scan_game(g, index) for g in games]
