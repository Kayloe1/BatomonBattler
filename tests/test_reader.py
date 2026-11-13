r"""Tests for the screen reader, run on saved captures.

    .venv\Scripts\python.exe -m unittest discover tests -v

Every capture in captures/ that has a "<name>.expected.json" beside it is read
and compared with that file. To add a test: save a capture, check the output of
"python reader.py <capture>" by eye, and save it as the .expected.json.
"""
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import reader  # noqa: E402
import window  # noqa: E402

CAPTURES = ROOT / "captures"


_comparable = reader.comparable


class PictureGeometry(unittest.TestCase):
    def test_bars_above_and_below(self):
        p = window.picture_rect(window.Rect(75, 200, 2560, 1600))
        self.assertEqual((p.left, p.top, p.width, p.height), (75, 280, 2560, 1440))

    def test_bars_left_and_right(self):
        p = window.picture_rect(window.Rect(0, 0, 2000, 900))
        self.assertEqual((p.left, p.top, p.width, p.height), (200, 0, 1600, 900))

    def test_exact_16_9_has_no_bars(self):
        p = window.picture_rect(window.Rect(10, 20, 1920, 1080))
        self.assertEqual((p.left, p.top, p.width, p.height), (10, 20, 1920, 1080))

    def test_fractions_skip_the_bars_and_round_trip(self):
        r = window.Rect(75, 200, 2560, 1600)
        self.assertEqual(window.frac_to_screen(r, 0, 0), (75, 280))
        self.assertEqual(window.frac_to_screen(r, 1, 1), (75 + 2559, 280 + 1439))
        for fx, fy in [(0.1, 0.9), (0.5, 0.5), (0.93, 0.07)]:
            x, y = window.frac_to_screen(r, fx, fy)
            bx, by = window.screen_to_frac(r, x, y)
            self.assertAlmostEqual(bx, fx, delta=0.001)
            self.assertAlmostEqual(by, fy, delta=0.001)

    def test_button_centre_lands_on_the_button(self):
        fx, fy = reader.box_to_frac(reader.BATTLE_BUTTON)
        x, y = window.frac_to_client(window.Rect(0, 0, 2560, 1600), fx, fy)
        img = Image.open(CAPTURES / "capture_20261111_101154_435562.png").convert("RGB")
        r, g, b = img.getpixel((x, y - 80))      # above the white "BATTLE!" letters
        self.assertTrue(r > 200 and g < 110 and b < 150, (r, g, b))


class SavedCaptures(unittest.TestCase):
    def test_every_labelled_capture(self):
        expected_files = sorted(CAPTURES.glob("*.expected.json"))
        self.assertTrue(expected_files, "no labelled captures found")
        for exp in expected_files:
            png = exp.with_name(exp.name.replace(".expected.json", ".png"))
            with self.subTest(capture=png.name):
                state = reader.read_state(Image.open(png))
                self.assertEqual(_comparable(state), json.loads(exp.read_text(encoding="utf-8")))

    def test_same_shop_with_a_different_background_frame(self):
        # Taken 5 minutes after the taught capture: same shop, the animated
        # background and the monsters' idle animation are in another frame.
        a = reader.read_state(Image.open(CAPTURES / "capture_20261111_101154_435562.png"))
        b = reader.read_state(Image.open(CAPTURES / "capture_20261111_101711_342762.png"))
        self.assertEqual(b["problems"], [])
        self.assertEqual(_comparable(a), _comparable(b))

    def test_covered_window_is_not_mistaken_for_a_screen(self):
        state = reader.read_state(Image.open(CAPTURES / "capture_20261111_101127_605046.png"))
        self.assertEqual(state["screen"], "unknown")
        self.assertTrue(state["problems"])

    def test_other_window_size_is_reported_as_a_problem(self):
        # The templates were cut at 2560x1440. At any other size the reader must
        # say so instead of returning numbers it cannot vouch for.
        img = Image.open(CAPTURES / "capture_20261111_101154_435562.png").convert("RGB")
        small = reader.read_state(img.resize((1920, 1200), Image.LANCZOS))
        self.assertEqual(small["screen"], "shop")
        self.assertTrue(any("templates need" in p for p in small["problems"]))


class ScreenDetection(unittest.TestCase):
    EXPECTED = {
        "matchmaking_day2.png": "matchmaking",
        "vs_day2.png": "unknown",              # VS animation: deliberately not a screen to act on
        "battle_day2.png": "battle",
        "result_win_day2.png": "result",
        "result_loss_day3.png": "result",
        "result_loss_day8.png": "result",
        "stats_day2.png": "stats",
        "event_dragon_hoard.png": "event",
        "event_baby_basilisk.png": "event",
        "event_mysterious_trainer.png": "event",
        "run_over_day8.png": "run_over",
        "shop_day7_swapped.png": "shop",
        "new_run_default.png": "new_run",
        "new_run_ranked_selected.png": "new_run",
        "trainer_pick.png": "trainer_pick",
        "gift_box.png": "gift_box",
        "trinket_pick.png": "trinket_pick",
        "shop_day1_broke.png": "shop",          # REROLL button is grey here ($0)
    }

    def test_each_screen(self):
        for name, screen in self.EXPECTED.items():
            with self.subTest(capture=name):
                state = reader.read_state(Image.open(CAPTURES / name))
                self.assertEqual(state["screen"], screen)
                if screen not in ("unknown",):
                    self.assertEqual(state["problems"], [])

    def test_events_have_three_choices(self):
        for name in ("event_dragon_hoard.png", "event_baby_basilisk.png", "event_mysterious_trainer.png"):
            self.assertEqual(reader.read_state(Image.open(CAPTURES / name))["choices"], 3, name)

    def test_fast_forward_is_seen_as_on(self):
        import numpy as np
        pic = np.asarray(window.canonical_picture(Image.open(CAPTURES / "battle_day2.png")))
        self.assertTrue(reader.fast_forward_on(pic))


class NewRunSafety(unittest.TestCase):
    """Rule 1: never start a Ranked run. The mode must be read correctly."""

    def test_casual_selected(self):
        s = reader.read_state(Image.open(CAPTURES / "new_run_default.png"))
        self.assertEqual((s["mode"], s["region"], s["problems"]), ("casual", "Pantra", []))

    def test_ranked_selected_is_reported_as_ranked(self):
        s = reader.read_state(Image.open(CAPTURES / "new_run_ranked_selected.png"))
        self.assertEqual(s["mode"], "ranked")

    def test_unclear_mode_is_none_with_a_problem(self):
        import numpy as np
        pic = np.asarray(window.canonical_picture(Image.open(CAPTURES / "new_run_default.png"))).copy()
        pic[1150:1320, 1290:1900] = (200, 200, 60)        # paint over the Casual button
        s = reader.read_new_run(pic)
        self.assertIsNone(s["mode"])
        self.assertTrue(s["problems"])

    def test_start_method_never_clicks_the_ranked_button(self):
        import inspect
        import hands
        src = inspect.getsource(hands.Hands.start_casual_run)
        self.assertNotIn("NEW_RUN_RANKED", src)
        self.assertNotIn("NEW_RUN_RANKED", inspect.getsource(__import__("play")))


class OtherScreens(unittest.TestCase):
    def test_trainer_names(self):
        s = reader.read_state(Image.open(CAPTURES / "trainer_pick.png"))
        self.assertEqual(s["trainers"], ["Witch", "Painter", "Monster Ranger"])

    def test_trinket_names(self):
        s = reader.read_state(Image.open(CAPTURES / "trinket_pick.png"))
        self.assertEqual(s["trinkets"], ["Fire Bell", "Poison Bell", "Power Crown"])

    def test_levels_two_and_three(self):
        s = reader.read_state(Image.open(CAPTURES / "shop_r2_day2_level2.png"))
        self.assertEqual(s["team"][5]["level"], 2)
        s = reader.read_state(Image.open(CAPTURES / "shop_r2_day7.png"))
        self.assertEqual(s["team"][5]["level"], 3)


class NameResolution(unittest.TestCase):
    def test_unknown_glyphs_resolve_only_when_unique(self):
        self.assertEqual(reader.resolve("Dri??let", reader.MONSTER_NAMES), "Dribblet")
        self.assertIsNone(reader.resolve("????????", reader.MONSTER_NAMES))
        self.assertIsNone(reader.resolve("Dribblex", reader.MONSTER_NAMES))
        self.assertEqual(reader.resolve("RICH LADY", reader.TRAINER_NAMES, ignore_case=True), "Rich Lady")


def _canonical(name: str):
    import numpy as np
    path = CAPTURES / name
    if not path.exists():
        return None
    return np.asarray(window.canonical_picture(Image.open(path).convert("RGB")))


class BattleScreen(unittest.TestCase):
    """Both teams read from the first frames of the Day 2 battle (checked by eye)."""

    def test_both_teams_at_battle_start(self):
        pic = _canonical("battle_day2.png")
        if pic is None:
            self.skipTest("captures/battle_day2.png not here")
        seen = reader.read_battle(pic)
        self.assertEqual(seen["problems"], [])

        def short(slot):
            return slot and (slot["name"], slot["level"], {b["stat"]: b["value"] for b in slot["stats"]})

        self.assertEqual([short(s) for s in seen["my_team"]], [
            ("Brawlmantis", 1, {"damage": 50}),
            ("Venopuff", 1, {"damage": 5, "poison": 4}),
            ("Dribblet", 1, {"heal": 20}),
            None,
            ("Mosslug", 1, {"damage": 5, "heal": 30}),
            ("Panbud", 1, {"damage": 25}),
        ])
        # The Dragon Egg (event reward) is never in the shop, so it has no card sprite to name it.
        self.assertEqual([short(s) for s in seen["opponent_team"]], [
            (None, 1, {"damage": 1}), None, None, ("Venopuff", 1, {"poison": 4}), None, None,
        ])


class CardSprites(unittest.TestCase):
    def test_every_shop_card_gives_a_sprite(self):
        pic = _canonical("shop_day1.png")
        if pic is None:
            self.skipTest("captures/shop_day1.png not here")
        state = reader.read_state(Image.open(CAPTURES / "shop_day1.png").convert("RGB"))
        for i, card in enumerate(state["shop"]):
            if card and card.get("name"):
                got = reader.card_sprite(pic, i)
                self.assertIsNotNone(got, card["name"])
                rgb, mask = got
                self.assertGreater(mask.mean(), 0.2, card["name"])


if __name__ == "__main__":
    unittest.main()


class Shiny(unittest.TestCase):
    """Shiny copies are told apart by their colour palette ("Name@shiny" sprite templates)."""

    def _read(self, name):
        path = CAPTURES / name
        if not path.exists():
            self.skipTest(f"captures/{name} not here")
        return reader.read_state(Image.open(path).convert("RGB"))

    def test_shiny_stingarde_and_magmite(self):
        st = self._read("manual_shop_day5_shiny_magmite_bench2_fumungus_team0.png")
        self.assertEqual((st["team"][2]["name"], st["team"][2].get("shiny")), ("Stingarde", True))
        self.assertEqual((st["bench"][2]["name"], st["bench"][2].get("shiny")), ("Magmite", True))
        self.assertFalse(st["team"][4].get("shiny"))          # a plain Magmite next to it

    def test_plain_stingarde_is_not_shiny(self):
        st = self._read("shop_r2_day3.png")
        self.assertEqual(st["team"][4]["name"], "Stingarde")
        self.assertFalse(st["team"][4].get("shiny"))


class ShinyShopCards(unittest.TestCase):
    def test_glimmer_shop_cards_are_shiny(self):
        path = CAPTURES / "manual_shop_glimmer_all_shiny_cards.png"
        if not path.exists():
            self.skipTest("captures/manual_shop_glimmer_all_shiny_cards.png not here")
        st = reader.read_state(Image.open(path).convert("RGB"))
        self.assertEqual([bool(c and c.get("shiny")) for c in st["shop"]], [True, False, True, True, True])

    def test_plain_shop_cards_are_not_shiny(self):
        path = CAPTURES / "shop_r2_day3.png"
        if not path.exists():
            self.skipTest("captures/shop_r2_day3.png not here")
        st = reader.read_state(Image.open(path).convert("RGB"))
        self.assertFalse(any(c and c.get("shiny") for c in st["shop"]))
