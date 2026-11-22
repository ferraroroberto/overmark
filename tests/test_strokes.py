"""Stroke model: board operations, undo, eraser, fading prune, laser trail."""

from overmark.strokes import Board, LaserTrail, Point, Stroke, Style, Tool

STYLE = Style("#FFE600", 6, outline_px=2)


def drawn(board: Board, *points: tuple[float, float], tool: Tool = Tool.PEN, at: float = 0.0):
    stroke = board.begin(Stroke(tool, STYLE, [Point(*p) for p in points[:1]]))
    for p in points[1:]:
        stroke.add_point(Point(*p))
    board.finish(stroke, at)
    return stroke


def test_add_and_undo() -> None:
    board = Board()
    first = drawn(board, (0, 0), (10, 0))
    second = drawn(board, (0, 20), (10, 20))
    assert board.strokes == [first, second]
    assert board.undo(1.0) is not None
    assert board.strokes == [first]
    board.undo(1.0)
    assert board.strokes == []
    assert board.undo(1.0) is None


def test_clear_is_undoable() -> None:
    board = Board()
    a, b = drawn(board, (0, 0)), drawn(board, (5, 5))
    assert board.clear() and board.strokes == []
    assert not board.clear()
    board.undo(2.0)
    assert board.strokes == [a, b]
    assert a.finished_at == 2.0  # restored ink starts a fresh fade delay


def test_eraser_removes_touched_strokes_and_undo_restores_order() -> None:
    board = Board()
    a = drawn(board, (0, 0), (100, 0))
    b = drawn(board, (0, 50), (100, 50))
    c = drawn(board, (0, 100), (100, 100))
    assert board.erase_at(50, 52, 4) == [b]
    assert board.strokes == [a, c]
    board.undo(0)
    assert board.strokes == [a, b, c]


def test_stroke_in_progress_is_not_erased_or_on_the_undo_stack() -> None:
    board = Board()
    active = board.begin(Stroke(Tool.PEN, STYLE, [Point(0, 0)]))
    assert board.erase_at(0, 0, 5) == []
    assert board.undo(0) is None
    assert board.strokes == [active]


def test_arrow_keeps_only_tail_and_tip() -> None:
    arrow = Stroke(Tool.ARROW, STYLE, [Point(0, 0), Point(0, 0)])
    for x in range(1, 50):
        arrow.add_point(Point(x, x))
    assert arrow.points == [Point(0, 0), Point(49, 49)]


def test_hit_test_counts_width_and_outline() -> None:
    stroke = Stroke(Tool.PEN, STYLE, [Point(0, 0), Point(100, 0)])
    assert stroke.hit(50, 5, 0)  # half width 3 + outline 2
    assert not stroke.hit(50, 6, 0)


def test_prune_drops_faded_strokes_and_their_undo_entries() -> None:
    board = Board()
    old = drawn(board, (0, 0), at=0.0)
    new = drawn(board, (5, 5), at=10.0)
    pinned = drawn(board, (9, 9), at=0.0)
    pinned.pinned = True
    assert board.prune(10.0, enabled=True, delay=5) == [old]
    assert board.strokes == [new, pinned]
    board.undo(10.0)
    board.undo(10.0)
    assert board.undo(10.0) is None  # the faded stroke's "add" entry went with it


def test_nothing_fades_when_fading_is_off() -> None:
    board = Board()
    drawn(board, (0, 0), at=0.0)
    assert board.prune(1e6, enabled=False, delay=1) == []
    assert not board.needs_fade_ticks(enabled=False)
    assert board.needs_fade_ticks(enabled=True)


def test_pin_all() -> None:
    board = Board()
    drawn(board, (0, 0))
    drawn(board, (1, 1))
    assert board.pin_all() == 2
    assert board.pin_all() == 0
    assert not board.needs_fade_ticks(enabled=True)


def test_highlighter_paints_first() -> None:
    board = Board()
    pen = drawn(board, (0, 0))
    hl = drawn(board, (0, 0), tool=Tool.HIGHLIGHTER)
    assert board.paint_order() == [hl, pen]


def test_laser_trail_is_never_on_the_board() -> None:
    board = Board()
    laser = LaserTrail(trail_seconds=0.25)
    for i in range(10):
        laser.add(i, i, i * 0.05)
    visible = laser.visible(0.45)
    assert board.strokes == [] and board.undo(0) is None
    assert all(age <= 1.0 for _, _, age in visible)
    assert visible[-1][:2] == (9, 9)
    remaining = laser.visible(10.0)
    assert len(remaining) == 1 and remaining[0][:2] == (9, 9)  # dot stays, trail is gone
