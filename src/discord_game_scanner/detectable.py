"""Download, cache and index Discord's public list of detectable applications."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DETECTABLE_URL = "https://discord.com/api/v9/applications/detectable"
CACHE_MAX_AGE = 24 * 3600
USER_AGENT = "discord-game-scanner/0.1 (+https://github.com/masteng0205)"


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / ("Library/Caches" if sys.platform == "darwin" else ".cache"))
    return Path(base) / "discord-game-scanner"


def host_exe_os() -> str:
    """Discord's name for the OS whose executable patterns apply to this machine."""
    return "darwin" if sys.platform == "darwin" else "win32"


def load_detectable(refresh: bool = False, timeout: float = 30.0) -> list[dict]:
    """Return the detectable list, using a 24h on-disk cache."""
    path = cache_dir() / "detectable.json"
    fresh = path.exists() and time.time() - path.stat().st_mtime < CACHE_MAX_AGE
    if fresh and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    req = urllib.request.Request(DETECTABLE_URL, headers={"User-Agent": USER_AGENT})
    try:
        # HTTPS with default certificate verification.
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("unexpected response shape")
    except Exception:
        if path.exists():  # offline fallback to a stale cache
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return data


@dataclass
class ExePattern:
    app: dict
    parts: tuple[str, ...]  # lower-case path components, last one is the .exe


@dataclass
class DetectableIndex:
    by_sku: dict[tuple[str, str], dict] = field(default_factory=dict)
    by_exe_name: dict[str, list[ExePattern]] = field(default_factory=dict)
    total: int = 0

    @classmethod
    def build(cls, apps: list[dict], exe_os: str = "win32") -> "DetectableIndex":
        idx = cls(total=len(apps))
        for app in apps:
            for sku in app.get("third_party_skus") or []:
                dist, sid = sku.get("distributor"), sku.get("id")
                if dist and sid:
                    idx.by_sku.setdefault((dist, str(sid).lower()), app)
            for exe in app.get("executables") or []:
                if exe.get("os") != exe_os or not exe.get("name"):
                    continue
                name = exe["name"].lower().lstrip(">").replace("\\", "/")
                parts = tuple(p for p in name.split("/") if p)
                if parts:
                    idx.by_exe_name.setdefault(parts[-1], []).append(ExePattern(app, parts))
        return idx

    def match_sku(self, distributor: str, sku_id: str) -> dict | None:
        return self.by_sku.get((distributor, str(sku_id).lower()))

    def match_exe(self, rel_parts: tuple[str, ...]) -> dict | None:
        """Match a lower-case relative exe path against Discord's patterns (suffix match)."""
        for pat in self.by_exe_name.get(rel_parts[-1], ()):
            n = len(pat.parts)
            if n <= len(rel_parts) and rel_parts[-n:] == pat.parts:
                return pat.app
        return None
