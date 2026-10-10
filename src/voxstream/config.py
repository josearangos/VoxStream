"""Service settings, read from ``VOXSTREAM_*`` environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOXSTREAM_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765
    enable_websocket: bool = True
    enable_grpc: bool = True
    grpc_port: int = 50051
    allow_non_local_bind: bool = False
    engine: str = "kokoro"
    max_text_chars: int = 2000
    request_timeout_s: float = 120
    idle_timeout_s: float = 15
    max_concurrent_requests: int = 1
    frame_ms: int = 100
    audio_queue_frames: int = 8
    max_pending_chars: int = 120
    execution_provider: str = "cpu"
    models_dir: str = "models"
    verification_file: str = "verification/voice-verification.json"
    default_voice: str | None = None
    allow_unverified_voices: bool = False
    verify_mean_wer: float = 0.15
    verify_max_sentence_wer: float = 0.35
    model_file: str = "kokoro-v1.0.onnx"
    voices_file: str = "voices-v1.0.bin"

    def validate_bind(self) -> None:
        """Binding anywhere but loopback requires an explicit opt-in (FR-022)."""
        if self.host not in ("127.0.0.1", "localhost", "::1") and not self.allow_non_local_bind:
            raise ValueError(
                f"Refusing to bind to {self.host!r}; set VOXSTREAM_ALLOW_NON_LOCAL_BIND=true "
                "to expose the service beyond localhost."
            )

    def validate_transports(self) -> None:
        """At least one transport must run, and the two listeners need distinct ports."""
        if not (self.enable_websocket or self.enable_grpc):
            raise ValueError(
                "At least one of the two transports must be enabled. Set "
                "VOXSTREAM_ENABLE_WEBSOCKET=true and/or VOXSTREAM_ENABLE_GRPC=true."
            )
        if (
            self.enable_websocket
            and self.enable_grpc
            and self.port == self.grpc_port
            and self.port != 0
        ):
            raise ValueError(
                f"VOXSTREAM_PORT and VOXSTREAM_GRPC_PORT are both {self.port}; "
                "choose different ports."
            )
