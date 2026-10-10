import io
import wave

from demo.audio import payload_ms, pcm_to_wav_chunk


def test_wav_header_and_roundtrip() -> None:
    pcm = b"\x01\x00" * 2400
    with wave.open(io.BytesIO(pcm_to_wav_chunk(pcm, 24000, 1))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 2400
        assert w.readframes(2400) == pcm


def test_payload_ms() -> None:
    assert payload_ms(b"\x00\x00" * 2400, 24000, 1) == 100
