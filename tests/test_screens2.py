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

    def test_cash_in(self):
        self.assertEqual(state("cash_in_fake_diamond.png")["screen"], "cash_in")

    def test_buttons_land_on_their_buttons(self):
        for name, box in (("main_menu.png", reader.MAIN_MENU_NEW_RUN), ("cash_in_fake_diamond.png", reader.CASH_IN_BUTTON)):
            pic = np.asarray(window.canonical_picture(Image.open(CAP / name)))
            x0, y0, x1, y1 = box
            red = reader._near(pic[y0:y1, x0:x1], (239, 66, 107), 40).mean()
            self.assertGreater(red, 0.5, name)      # the box sits on the red button (text aside)

    def test_other_screens_not_mistaken(self):
        for name in ("stats_day2.png", "result_loss_day3.png"):
            self.assertNotIn(state(name)["screen"], ("main_menu", "cash_in"))


if __name__ == "__main__":
    unittest.main()
