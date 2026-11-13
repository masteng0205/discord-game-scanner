import json
import tempfile
import unittest
from pathlib import Path

from discord_game_scanner import vdf
from discord_game_scanner.detectable import DetectableIndex
from discord_game_scanner.libraries import InstalledGame
from discord_game_scanner.scanner import scan_game

APPS = [
    {"id": "1", "name": "World of Warcraft",
     "executables": [{"os": "win32", "name": "_retail_/wow.exe"}]},
    {"id": "2", "name": "Rocket League",
     "executables": [{"os": "win32", "name": "rocketleague.exe"}],
     "third_party_skus": [{"distributor": "steam", "id": "252950"},
                          {"distributor": "epic", "id": "9773AA1AA54F4F7B80E44BEF04986CEA"}]},
    {"id": "3", "name": "Garry's Mod",
     "executables": [{"os": "win32", "name": ">garrysmod/hl2.exe"}, {"os": "darwin", "name": "hl2_osx"}]},
]


class VdfTests(unittest.TestCase):
    def test_nested_and_escapes(self):
        text = '"libraryfolders"\n{\n "0"\n {\n  "path"\t\t"D:\\\\Steam"\n  "apps" { "10" "123" }\n }\n}\n'
        data = vdf.loads(text)
        self.assertEqual(data["libraryfolders"]["0"]["path"], "D:\\Steam")
        self.assertEqual(data["libraryfolders"]["0"]["apps"]["10"], "123")

    def test_case_insensitive_get(self):
        data = vdf.loads('"A" { "LastPlayed" "5" }')
        self.assertEqual(vdf.get_ci(data, "a", "lastplayed"), "5")
        self.assertIsNone(vdf.get_ci(data, "a", "missing"))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.idx = DetectableIndex.build(APPS)

    def test_sku_case_insensitive(self):
        self.assertEqual(self.idx.match_sku("epic", "9773aa1aa54f4f7b80e44bef04986cea")["id"], "2")
        self.assertIsNone(self.idx.match_sku("steam", "999"))

    def test_exe_suffix_match(self):
        self.assertEqual(self.idx.match_exe(("world of warcraft", "_retail_", "wow.exe"))["id"], "1")
        self.assertIsNone(self.idx.match_exe(("world of warcraft", "_classic_", "wow.exe")))
        self.assertEqual(self.idx.match_exe(("garrysmod", "hl2.exe"))["id"], "3")

    def test_non_windows_ignored(self):
        self.assertNotIn("hl2_osx", self.idx.by_exe_name)


class ScanTests(unittest.TestCase):
    def test_exe_found_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "World of Warcraft")
            (root / "_retail_").mkdir(parents=True)
            (root / "_retail_" / "Wow.exe").write_bytes(b"")
            game = InstalledGame("steam", "0", "WoW", root)
            r = scan_game(game, DetectableIndex.build(APPS))
            self.assertEqual((r.method, r.discord_app["id"]), ("exe", "1"))

    def test_sku_without_files(self):
        game = InstalledGame("steam", "252950", "Rocket League", Path("Z:/nope"))
        r = scan_game(game, DetectableIndex.build(APPS))
        self.assertEqual((r.method, r.discord_app["id"]), ("sku", "2"))

    def test_not_detectable(self):
        game = InstalledGame("steam", "1", "Some Tool", Path("Z:/nope"))
        self.assertFalse(scan_game(game, DetectableIndex.build(APPS)).detectable)


class OwnedTests(unittest.TestCase):
    def test_normalize_name(self):
        from discord_game_scanner.steam_api import normalize_name
        self.assertEqual(normalize_name("HELLDIVERS™ 2"), normalize_name("Helldivers 2"))

    def test_candidates_filter_and_order(self):
        from discord_game_scanner.cli import owned_candidates
        from discord_game_scanner.steam_api import OwnedGame
        owned = [
            OwnedGame("252950", "Rocket League", 600, 1_700_000_000),
            OwnedGame("1", "Not In Discord", 0, None),
            OwnedGame("999", "Installed Game", 0, None),
        ]
        apps = APPS + [{"id": "9", "name": "Installed Game",
                        "third_party_skus": [{"distributor": "steam", "id": "999"}]}]
        idx = DetectableIndex.build(apps)
        rows = owned_candidates(owned, idx, installed_ids={"999"}, excludes=set())
        self.assertEqual([g.name for g, _ in rows], ["Rocket League"])
        self.assertEqual(owned_candidates(owned, idx, set(), {"rocketleague"})[0][0].name, "Installed Game")

    def test_missing_key_without_cache(self):
        import os
        from unittest import mock
        from discord_game_scanner import cli
        from discord_game_scanner.steam_api import SteamApiError
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}, clear=False):
            os.environ.pop("STEAM_API_KEY", None)
            with self.assertRaises(SteamApiError):
                cli.load_owned("76561198000000000")

    def test_fmt_playtime(self):
        from discord_game_scanner.cli import _fmt_playtime
        self.assertEqual(_fmt_playtime(0), "0")
        self.assertEqual(_fmt_playtime(2), "<0.1 h")
        self.assertEqual(_fmt_playtime(90), "1.5 h")

    def test_print_owned_sections_limit_and_never_only(self):
        import io
        from contextlib import redirect_stdout
        from discord_game_scanner.cli import print_owned
        from discord_game_scanner.steam_api import OwnedGame
        rows = [(OwnedGame(str(i), f"Never{i}", 0, None), {}) for i in range(3)] + \
               [(OwnedGame(str(10 + i), f"Played{i}", 60, 1_600_000_000), {}) for i in range(3)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            never = print_owned(rows, 6, "test", limit=2)
        out = buf.getvalue()
        self.assertEqual([g.name for g in never], ["Never0", "Never1", "Never2"])
        self.assertIn("NEVER PLAYED", out)
        self.assertIn("Played on Steam", out)
        self.assertNotIn("Never2", out)            # cut by limit=2
        self.assertIn("and 1 more", out)
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_owned(rows, 6, "test", limit=0, never_only=True)
        self.assertNotIn("Played0", buf.getvalue())

    def test_api_error_falls_back_to_cache(self):
        import json, os
        from unittest import mock
        from discord_game_scanner import cli
        from discord_game_scanner.steam_api import SteamApiError
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp, "STEAM_API_KEY": "x"}), \
                mock.patch.object(cli, "get_owned_games", side_effect=SteamApiError("HTTP 403")):
            cache = cli._owned_cache("76561198000000000")
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps([{"appid": "1", "name": "A", "playtime_min": 0, "last_played": None}]))
            owned, source = cli.load_owned("76561198000000000")
        self.assertEqual([g.name for g in owned], ["A"])
        self.assertIn("cached", source)

    def test_error_never_leaks_key(self):
        from unittest import mock
        import urllib.error
        from discord_game_scanner import steam_api
        err = urllib.error.HTTPError("https://x/?key=SECRET123", 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(steam_api.SteamApiError) as ctx:
                steam_api.get_owned_games("76561198000000000", api_key="SECRET123")
        self.assertNotIn("SECRET123", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
