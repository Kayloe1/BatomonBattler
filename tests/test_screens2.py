"""Main menu and the Cash In trinket dialog."""
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import reader
import window

CAP = Path(__file__).resolve().parent.parent / "captures"


def state(name):
    return reader.read_state(Image.open(CAP / name))


class NewScreens(unittest.TestCase):
    def test_main_menu(self):
        self.assertEqual(state("main_menu.png")["screen"], "main_menu")

    def test_menu_with_a_run_open_is_its_own_screen(self):
        self.assertEqual(state("main_menu_continue.png")["screen"], "main_menu_continue")
        self.assertEqual(state("main_menu.png")["screen"], "main_menu")

    def test_new_run_box_is_never_on_a_button_of_the_continue_menu(self):
        # on the five-button menu the New Run box of the four-button menu must not hit New Run
        pic = np.asarray(window.canonical_picture(Image.open(CAP / "main_menu_continue.png")))
        x0, y0, x1, y1 = reader.MAIN_MENU_CONTINUE
        self.assertGreater(reader._near(pic[y0:y1, x0:x1], (239, 66, 107), 40).mean(), 0.5)
        self.assertLess(y1, 796)            # the Continue box ends above the New Run button (starts at y 796)

    def test_continue_panel_reads_casual(self):
        st = state("continue_confirm_casual.png")
        self.assertEqual(st["screen"], "continue_confirm")
        self.assertEqual(st["mode"], "casual")

    def test_continue_panel_refuses_any_other_label(self):
        pic = np.asarray(window.canonical_picture(Image.open(CAP / "continue_confirm_casual.png"))).copy()
        x0, y0, x1, y1 = reader.CONTINUE_MODE_LABEL
        label = pic[y0:y1, x0:x1].copy()
        # a longer label (as "RANKED MODE" or anything unseen would be): not casual
        pic[y0:y1, x0 + 60:x1] = label[:, :-60]
        self.assertIsNone(reader.continue_mode(pic))
        # no label at all: not casual
        pic[y0:y1, x0:x1] = 255
        self.assertIsNone(reader.continue_mode(pic))

    def test_continue_buttons(self):
        pic = np.asarray(window.canonical_picture(Image.open(CAP / "continue_confirm_casual.png")))
        for box in (reader.CONTINUE_CONFIRM, reader.CONTINUE_CANCEL):
            x0, y0, x1, y1 = box
            self.assertGreater(reader._near(pic[y0:y1, x0:x1], (239, 66, 107), 40).mean(), 0.5)
        self.assertGreater(reader.CONTINUE_CONFIRM[0], reader.CONTINUE_CANCEL[2])

    def test_select_target_screen(self):
        st = state("select_target.png")
        self.assertEqual(st["screen"], "select_target")
        self.assertFalse(st["confirm_enabled"])
        self.assertIsNone(st["team"][0])
        self.assertEqual([b["value"] for b in st["team"][1]["stats"]], [150])
        self.assertEqual(st["bench"], [None] * 4)
        pic = np.asarray(window.canonical_picture(Image.open(CAP / "select_target.png")))
        x0, y0, x1, y1 = reader.TARGET_BACK
        self.assertGreater(reader._near(pic[y0:y1, x0:x1], (239, 66, 107), 40).mean(), 0.5)
        self.assertLess(reader.TARGET_CONFIRM[2], reader.TARGET_BACK[0])     # Confirm never overlaps Back

    def test_title(self):
        self.assertEqual(state("title_screen.png")["screen"], "title")
        self.assertEqual(state("title_screen.png")["problems"], [])

    def test_cash_in(self):
        self.assertEqual(state("cash_in_fake_diamond.png")["screen"], "cash_in")

    def test_buttons_land_on_their_buttons(self):
        for name, box in (("main_menu.png", reader.MAIN_MENU_NEW_RUN), ("cash_in_fake_diamond.png", reader.CASH_IN_BUTTON),
                          ("main_menu_continue.png", reader.MAIN_MENU_CONTINUE)):
            pic = np.asarray(window.canonical_picture(Image.open(CAP / name)))
            x0, y0, x1, y1 = box
            red = reader._near(pic[y0:y1, x0:x1], (239, 66, 107), 40).mean()
            self.assertGreater(red, 0.5, name)      # the box sits on the red button (text aside)

    def test_event_effect_lines_are_read(self):
        self.assertEqual(state("event_dragon_hoard.png")["effects"],
                         ["Gain Dragon Egg", "Gain Hero's Sword", "Gain $20"])
        self.assertEqual(state("event_20261112_132759.png")["effects"],
                         ["Gain a foreign Rare monster. It can now appear in your shop.", "Gain Kaleidoscope",
                          "Gain Fake Diamond"])
        self.assertEqual(state("event_20261112_090216.png")["effects"][1],
                         "Give a monster Electric typing and +5 Shock")
        self.assertEqual(state("event_20261112_133833.png")["choices"], 3)

    def test_other_screens_not_mistaken(self):
        for name in ("stats_day2.png", "result_loss_day3.png"):
            self.assertNotIn(state(name)["screen"], ("main_menu", "cash_in"))


if __name__ == "__main__":
    unittest.main()
