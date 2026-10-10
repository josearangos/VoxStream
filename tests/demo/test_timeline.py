from demo.timeline import build_timeline

TEXT = "Hola, ¿cómo estás?\nMe alegra verte. Año 2024: ñandú"


def test_monotonic_and_offsets() -> None:
    tl = build_timeline(TEXT, 14)
    prev = 0.0
    for w in tl.words:
        assert w.start_s == prev and w.end_s > w.start_s
        assert TEXT[w.char_start : w.char_end] == w.text
        prev = w.end_s
    assert [w.text for w in tl.words][:3] == ["Hola,", "¿cómo", "estás?"]


def test_pause_weights() -> None:
    tl = build_timeline("a, b. c\nd", 1, pause_comma=3, pause_sentence=6, pause_linebreak=8)
    assert [w.weight for w in tl.words] == [5, 8, 9, 1]


def test_rescale_ends_exactly() -> None:
    tl = build_timeline(TEXT, 14)
    tl.rescale(12.5)
    assert abs(tl.total_s - 12.5) < 1e-9
    assert tl.words[0].start_s == 0


def test_word_at_clamps() -> None:
    tl = build_timeline("uno dos tres", 4)
    assert tl.word_at(-5) == 0
    assert tl.word_at(0) == 0
    assert tl.word_at(tl.words[1].start_s) == 1
    assert tl.word_at(999) == 2


def test_punctuation_only_and_empty() -> None:
    assert [w.text for w in build_timeline("... ¿¡ !!", 10).words] == ["...", "¿¡", "!!"]
    empty = build_timeline("  \n ", 10)
    assert len(empty) == 0 and empty.word_at(1) == -1
    empty.rescale(3)
    empty.reanchor(1, 0)


def test_multiline_and_numbers() -> None:
    tl = build_timeline("uno\n\ndos 3,5", 10)
    assert [w.text for w in tl.words] == ["uno", "dos", "3,5"]


def test_reanchor_shifts_later_only() -> None:
    tl = build_timeline("uno dos tres cuatro", 4)
    before = [(w.start_s, w.end_s) for w in tl.words]
    tl.reanchor(before[2][0] + 0.5, 2)
    after = [(w.start_s, w.end_s) for w in tl.words]
    assert after[:2] == before[:2]
    assert abs(after[2][0] - (before[2][0] + 0.5)) < 1e-9
    assert abs((after[3][1] - after[3][0]) - (before[3][1] - before[3][0])) < 1e-9
    assert after[3][0] == after[2][1]
