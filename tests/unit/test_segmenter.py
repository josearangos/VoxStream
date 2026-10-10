import pytest

from voxstream.core.segmenter import Segmenter


def run(pieces, max_pending=120):
    s = Segmenter(max_pending_chars=max_pending)
    out = []
    for p in pieces:
        out += s.push(p)
    out += s.flush()
    return out


def texts(segs):
    return [s.text for s in segs]


def test_splits_on_terminators():
    segs = run(["Hola. ¿Cómo estás? ¡Bien! Sí; claro… ok\nfin"])
    assert texts(segs) == ["Hola.", "¿Cómo estás?", "¡Bien!", "Sí;", "claro…", "ok", "fin"]
    assert [s.index for s in segs] == list(range(7))


def test_reasons():
    segs = run(["Hola. Resto sin punto"])
    assert [s.reason for s in segs] == ["sentence_end", "end_of_text"]


@pytest.mark.parametrize(
    "text",
    [
        "El Sr. García llegó.",
        "La Sra. López y el Dr. Pérez hablaron.",
        "La Dra. Ruiz vino.",
        "Compré pan, leche, etc. y salí.",
        "Véase la pág. 12 del libro.",
        "El valor es 3.5 y subió.",
        "Pagó 1.000.000 pesos.",
    ],
)
def test_no_split_inside(text):
    assert texts(run([text])) == [text]


def test_ellipsis_with_dots_splits_after_run():
    assert texts(run(["Bueno... sigamos."])) == ["Bueno...", "sigamos."]


def test_period_at_end_of_buffer_waits_for_context():
    s = Segmenter()
    assert s.push("Mide 3.") == []
    assert s.push("5 metros. Listo") and True
    assert texts(s.flush()) == ["Listo"]


def test_decimal_split_across_pieces_not_cut():
    segs = run(["Mide 3.", "5 metros. Fin."])
    assert texts(segs) == ["Mide 3.5 metros.", "Fin."]


def test_sentence_end_emitted_when_whitespace_arrives():
    s = Segmenter()
    assert s.push("Hola mundo.") == []
    out = s.push(" Adiós")
    assert texts(out) == ["Hola mundo."]
    assert texts(s.flush()) == ["Adiós"]


def test_question_emits_immediately():
    s = Segmenter()
    assert texts(s.push("¿Qué tal?")) == ["¿Qué tal?"]


def test_pieces_split_words_and_accents():
    segs = run(["La can", "ción del ni", "ño es be", "lla. Más a", "llá."])
    assert texts(segs) == ["La canción del niño es bella.", "Más allá."]


def test_accents_enye_and_english_words_preserved():
    text = "El niño bebió un smoothie en el café. Mañana vendrá el manager."
    segs = run([text])
    assert texts(segs) == ["El niño bebió un smoothie en el café.", "Mañana vendrá el manager."]


def test_fallback_cut_at_last_comma():
    text = "uno dos tres cuatro cinco seis siete, ocho nueve diez once doce trece"
    s = Segmenter(max_pending_chars=40)
    out = s.push(text)
    assert out and out[0].reason == "fallback_length"
    assert out[0].text == "uno dos tres cuatro cinco seis siete,"


def test_fallback_cut_at_space_when_no_comma():
    s = Segmenter(max_pending_chars=20)
    out = s.push("palabra " * 6)
    assert out[0].reason == "fallback_length"
    assert out[0].text == "palabra palabra"


def test_flush_unterminated_remainder():
    segs = run(["Sin punto final"])
    assert texts(segs) == ["Sin punto final"] and segs[0].reason == "end_of_text"


def test_whitespace_only_ignored():
    assert run(["   ", "\n  "]) == []


def test_concatenation_equals_normalized_input():
    text = "Hola,  Sr. Pérez.  Mide 3.5 cm...  ¿Sí?  No; tal vez\nbien. Fin"
    for size in (1, 3, 7, 1000):
        pieces = [text[i : i + size] for i in range(0, len(text), size)]
        segs = run(pieces)
        assert " ".join(texts(segs)) == " ".join(text.split())


def test_incremental_equals_whole():
    text = "Primera frase. Segunda frase, con coma. Tercera sin fin"
    whole = texts(run([text]))
    chunked = texts(run([text[i : i + 4] for i in range(0, len(text), 4)]))
    assert whole == chunked


def test_closing_quote_stays_with_sentence():
    assert texts(run(['Dijo "hola." Luego salió.'])) == ['Dijo "hola."', "Luego salió."]
