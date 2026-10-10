from demo.teleprompter import render
from demo.timeline import build_timeline

TEXT = "uno dos\n  tres"


def _words() -> list:
    return build_timeline(TEXT, 10).words


def test_classes_per_index() -> None:
    html = render(TEXT, _words(), 1, False)
    assert '<span class="spoken">uno</span>' in html
    assert '<span class="current" id="tp-current">dos</span>' in html
    assert '<span class="upcoming">tres</span>' in html


def test_escaping() -> None:
    text = "<script>x</script> & y"
    html = render(text, build_timeline(text, 10).words, 0, False)
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html


def test_whitespace_preserved() -> None:
    html = render(TEXT, _words(), 0, False)
    assert "dos</span>\n  <span" in html


def test_finished_all_spoken() -> None:
    html = render(TEXT, _words(), 0, True)
    assert "current" not in html and html.count('class="spoken"') == 3
