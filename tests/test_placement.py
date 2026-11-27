"""The toolbar's saved spot: layout key, default fallback, staying on screen."""

from overmark.placement import Area, clamp_anchor, layout_key, nearest, resolve_anchor, top_left

LEFT = Area(0, 0, 1920, 1040)
RIGHT = Area(1920, 0, 2560, 1400)


def test_layout_key_ignores_order_and_changes_with_the_monitors() -> None:
    assert layout_key([LEFT, RIGHT]) == layout_key([RIGHT, LEFT])
    assert layout_key([LEFT, RIGHT]) != layout_key([LEFT])


def test_saved_spot_is_used_on_the_screen_that_holds_it() -> None:
    assert resolve_anchor((2500, 300), [LEFT, RIGHT], LEFT, 12) == ((2500, 300), RIGHT)


def test_no_spot_or_an_off_screen_spot_falls_back_to_top_centre() -> None:
    default = ((959, 12), LEFT)
    assert resolve_anchor(None, [LEFT], LEFT, 12) == default
    assert resolve_anchor((2500, 300), [LEFT], LEFT, 12) == default  # monitor removed


def test_short_and_long_pill_share_the_anchor_and_stay_on_screen() -> None:
    assert top_left((900, 100), 60, 52, LEFT) == (870, 100)
    assert top_left((900, 100), 800, 52, LEFT) == (500, 100)
    # Near an edge the long pill slides in and still covers the short one.
    assert top_left((10, 100), 60, 52, LEFT) == (0, 100)
    assert top_left((10, 100), 800, 52, LEFT) == (0, 100)
    assert top_left((1919, 1039), 800, 52, LEFT) == (1120, 988)


def test_a_drop_outside_is_pulled_back_to_the_nearest_screen() -> None:
    assert nearest([LEFT, RIGHT], (4600, 700)) == RIGHT
    assert clamp_anchor((-200, -5), LEFT, 52) == (0, 0)
    assert clamp_anchor((5000, 1399), RIGHT, 52) == (4479, 1348)
