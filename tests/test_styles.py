import unittest

from qgis2squidmaps import styles


class StylesTest(unittest.TestCase):

    def test_hex_color(self):
        self.assertEqual(styles.hex_color(63, 128, 196), "#3F80C4")
        self.assertEqual(styles.hex_color(300, -1, 0), "#FF0000")

    def test_circle_radius_is_half_the_diameter_and_clamped(self):
        self.assertEqual(styles.circle_radius(20), 10)
        self.assertEqual(styles.circle_radius(1), 2)
        self.assertEqual(styles.circle_radius(500), 40)

    def test_hairline_width(self):
        self.assertEqual(styles.line_width(0), 1)
        self.assertEqual(styles.line_width(0.1), 0.5)
        self.assertEqual(styles.line_width(99), 20)

    def test_opacity_multiplies(self):
        self.assertEqual(styles.opacity(0.5, 0.5), 0.25)
        self.assertEqual(styles.opacity(1, None, 0.8), 0.8)

    def test_dasharray(self):
        self.assertEqual(styles.dasharray("solid"), [])
        self.assertEqual(styles.dasharray("dash"), [4, 2])
        self.assertEqual(styles.dasharray("dashdotdot"), [4, 2, 1, 2, 1, 2])
        # Custom patterns are in pixels; squidmaps wants line widths.
        self.assertEqual(styles.dasharray("custom", [10, 5], 5), [2, 1])
        # Odd-length patterns are trimmed to dash/gap pairs.
        self.assertEqual(styles.dasharray("custom", [3, 3, 3], 1), [3, 3])
        self.assertEqual(len(styles.dasharray("custom", [1] * 20, 1)), 8)

    def test_popup_markdown(self):
        md = styles.popup_markdown([
            ("Name", "Joe's *Diner*"),
            ("Empty", None),
            ("Blank", "  "),
            ("Site", "https://example.com/a_b"),
            ("Notes", "line one\nline two"),
        ])
        self.assertEqual(md, "\n\n".join([
            "**Name**: Joe's \\*Diner\\*",
            "**Site**: [https://example.com/a\\_b](https://example.com/a_b)",
            "**Notes**: line one  \nline two",
        ]))

    def test_slug(self):
        self.assertEqual(styles.slug("Bike Lanes (2024)"), "bike-lanes-2024")
        self.assertEqual(styles.slug("!!!"), "layer")

    def test_truncate(self):
        self.assertEqual(styles.truncate("abc", 5), "abc")
        self.assertEqual(len(styles.truncate("a" * 200, 100)), 100)

    def test_zoom_for_bounds(self):
        z = styles.zoom_for_bounds([-74.02, 40.7, -73.95, 40.75])
        self.assertTrue(12 < z < 15, z)
        self.assertEqual(styles.zoom_for_bounds([-180, -85, 180, 85]), 1.65)


if __name__ == "__main__":
    unittest.main()
