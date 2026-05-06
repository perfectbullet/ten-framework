import asyncio
from datetime import datetime
import json

from .config import CosyTTSConfig
from ten_runtime.async_ten_env import AsyncTenEnv
from .local_speech_synthesizer import (
    LocalSpeechSynthesizer,
    AudioFormat as LocalAudioFormat,
)


MESSAGE_TYPE_PCM = 1
MESSAGE_TYPE_CMD_COMPLETE = 2
MESSAGE_TYPE_CMD_ERROR = 3
MESSAGE_TYPE_CMD_CANCEL = 4
MESSAGE_TYPE_CMD_RESULT_GENERATED = 5

ERROR_CODE_TTS_FAILED = -1

# Audio format mapping constants for Local Service
LOCAL_AUDIO_FORMAT_MAPPING = {
    8000: LocalAudioFormat.PCM_8000HZ_MONO_16BIT,
    16000: LocalAudioFormat.PCM_16000HZ_MONO_16BIT,
    22050: LocalAudioFormat.PCM_22050HZ_MONO_16BIT,
    24000: LocalAudioFormat.PCM_24000HZ_MONO_16BIT,
    44100: LocalAudioFormat.PCM_44100HZ_MONO_16BIT,
    48000: LocalAudioFormat.PCM_48000HZ_MONO_16BIT,
}
DEFAULT_LOCAL_AUDIO_FORMAT = LocalAudioFormat.PCM_16000HZ_MONO_16BIT


class CosyTTSTaskFailedException(Exception):
    """Exception raised when Cosy TTS task fails"""

    error_code: int
    error_msg: str

    def __init__(self, error_code: int, error_msg: str):
        self.error_code = error_code
        self.error_msg = error_msg
        super().__init__(f"TTS task failed: {error_msg} (code: {error_code})")


class AsyncIteratorCallback:
    """Callback class for handling TTS synthesis results asynchronously."""

    def __init__(
        self,
        ten_env: AsyncTenEnv,
        queue: asyncio.Queue[tuple[bool, int, str | bytes | None]],
    ) -> None:
        self.ten_env = ten_env

        self._closed = False
        self._cancelled = False
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def close(self):
        """Close the callback."""
        self._closed = True

    def cancel(self):
        """Cancel the callback, filtering out further audio output."""
        self._cancelled = True
        self.ten_env.log_info(
            "AsyncIteratorCallback cancelled, will filter audio output"
        )

    def on_open(self):
        """Called when WebSocket connection opens."""
        self.ten_env.log_info("WebSocket connection opened for TTS synthesis.")

    def on_complete(self):
        """Called when TTS synthesis completes successfully."""
        self.ten_env.log_info("TTS synthesis task completed successfully.")

        # Send completion signal only if not cancelled and not closed
        if not self._cancelled and not self._closed:
            asyncio.run_coroutine_threadsafe(
                self._queue.put((True, MESSAGE_TYPE_CMD_COMPLETE, None)),
                self._loop,
            )

    def on_error(self, message: str):
        """Called when TTS synthesis encounters an error."""
        self.ten_env.log_error(f"TTS synthesis task failed: {message}")

        # Send error signal only if not cancelled and not closed
        if not self._cancelled and not self._closed:
            asyncio.run_coroutine_threadsafe(
                self._queue.put((False, MESSAGE_TYPE_CMD_ERROR, message)),
                self._loop,
            )

    def on_close(self):
        """Called when WebSocket connection closes."""
        self.ten_env.log_info("WebSocket connection closed.")
        self.close()

    def on_event(self, message: str) -> None:
        """Called when receiving events from TTS service."""
        if not self._cancelled:
            try:
                event_data = json.loads(message)
                if (
                    event_data.get("header", {}).get("event")
                    == "result-generated"
                ):
                    char_count = (
                        event_data.get("payload", {})
                        .get("usage", {})
                        .get("characters")
                    )
                    if isinstance(char_count, int):
                        asyncio.run_coroutine_threadsafe(
                            self._queue.put(
                                (
                                    False,
                                    MESSAGE_TYPE_CMD_RESULT_GENERATED,
                                    char_count,
                                )
                            ),
                            self._loop,
                        )
            except json.JSONDecodeError:
                self.ten_env.log_error("Failed to decode TTS event JSON")
            except Exception as e:
                self.ten_env.log_error(f"Error processing TTS event: {e}")

    def on_data(self, data: bytes) -> None:
        """Called when receiving audio data from TTS service."""
        if self._closed:
            self.ten_env.log_warn(
                f"Received {len(data)} bytes but connection was closed"
            )
            return

        if self._cancelled:
            self.ten_env.log_debug(
                f"Filtered {len(data)} bytes audio data due to cancellation"
            )
            return

        self.ten_env.log_info(f"Received audio data: {len(data)} bytes")
        # Send audio data to queue
        asyncio.run_coroutine_threadsafe(
            self._queue.put((False, MESSAGE_TYPE_PCM, data)), self._loop
        )


class CosyTTSClient:
    """Client for local CosyVoice WebSocket TTS service."""

    def __init__(
        self,
        config: CosyTTSConfig,
        ten_env: AsyncTenEnv,
        vendor: str,
    ):
        # Configuration and environment
        self.config = config
        self.ten_env = ten_env
        self.vendor = vendor

        # TTS synthesizer
        self._callback: AsyncIteratorCallback | None = None
        self.synthesizer: LocalSpeechSynthesizer | None = None

        # Communication queue for audio data - shared across all requests
        self._receive_queue: asyncio.Queue[
            tuple[bool, int, str | bytes | None]
        ] = asyncio.Queue()

        # Flag to track if client is started
        self._started = False

    def start(self) -> None:
        """Start the TTS client and initialize components."""

        # If already started with valid callback and queue, just ensure synthesizer exists
        if self._started and self._callback and not self._callback._closed:
            self.ten_env.log_info(
                "Client already started, checking synthesizer..."
            )
            if self.synthesizer is None:
                self._create_synthesizer()
            return

        # Close old callback if exists
        if self._callback:
            self.ten_env.log_info(
                "Closing old callback before creating new one"
            )
            self._callback.close()
            self._callback = None

        # Close old synthesizer if exists
        if self.synthesizer:
            self.ten_env.log_info(
                "Closing old synthesizer before creating new one"
            )
            try:
                self.synthesizer.close()
            except Exception as e:
                self.ten_env.log_warn(f"Error closing old synthesizer: {e}")
            self.synthesizer = None

        # Initialize audio data callback with the SHARED queue
        self._callback = AsyncIteratorCallback(
            self.ten_env, self._receive_queue
        )
        self.ten_env.log_info(
            "Created new AsyncIteratorCallback with shared queue"
        )

        # Create synthesizer
        self._create_synthesizer()

        self._started = True
        self.ten_env.log_info("Cosy TTS client started successfully")

    def _create_synthesizer(self) -> None:
        """Create a new synthesizer instance."""
        # Use local_spk_id if set, otherwise use voice as speaker ID
        speaker_id = (
            self.config.local_spk_id
            if self.config.local_spk_id
            else self.config.voice
        )
        self.synthesizer = LocalSpeechSynthesizer(
            callback=self._callback,
            format=self._get_audio_format(),
            model=self.config.model,
            voice=speaker_id,
            url=self.config.local_service_url,
        )
        self.ten_env.log_info(
            f"Created new synthesizer for local TTS service at {self.config.local_service_url}"
        )

    def cancel(self) -> None:
        """
        Cancel current TTS operation and close WebSocket connection.
        Note: Does NOT destroy the callback or queue, only the synthesizer.
        """
        # Cancel callback to filter out remaining audio
        if self._callback:
            self._callback.cancel()
            self.ten_env.log_info("Cancelled callback (filtering audio)")

        if self.synthesizer:
            try:
                self.synthesizer.streaming_cancel()
                self.ten_env.log_info("Cancelled TTS streaming")

                # Close WebSocket connection to ensure clean state
                self.synthesizer.close()
                self.ten_env.log_info("Closed WebSocket connection")
            except Exception as e:
                self.ten_env.log_error(f"Error cancelling TTS: {e}")

            # Clean up synthesizer only - keep callback and queue
            self.synthesizer = None
            self.ten_env.log_info(
                "TTS synthesizer cleaned up, callback preserved"
            )

        # Put cancel message in queue to notify consumer
        try:
            self._receive_queue.put_nowait(
                (False, MESSAGE_TYPE_CMD_CANCEL, "cancelled")
            )
        except Exception:
            pass

    def complete(self) -> None:
        """
        Complete current TTS operation and signal end of text input.
        Note: Does NOT close the connection - that happens when done=True is received.
        """
        if self.synthesizer:
            try:
                # Only signal completion to server, don't close connection yet
                self.synthesizer.async_streaming_complete()
                self.ten_env.log_info(
                    "TTS streaming complete signal sent (waiting for audio response...)"
                )
            except Exception as e:
                self.ten_env.log_error(f"Error completing TTS: {e}")

            # ✅ IMPORTANT: Do NOT set synthesizer to None here!
            # Keep it alive to receive audio response from server.
            # It will be cleaned up when done=True is received.

    def synthesize_audio(self, text: str, text_input_end: bool):
        """
        Start audio synthesis for the given text.
        This method only initiates synthesis and returns immediately.
        Audio data should be consumed from the queue independently.
        """
        self.ten_env.log_info(
            f"Starting TTS synthesis, text: {text}, input_end: {text_input_end}"
        )

        # Check if synthesizer exists but is disconnected (e.g., server closed connection)
        if self.synthesizer is not None and not self.synthesizer.connected:
            self.ten_env.log_warn(
                "Synthesizer disconnected, will recreate connection..."
            )
            self.synthesizer = None

        # Also check if callback is closed (connection was closed)
        if self.synthesizer is not None and self._callback and self._callback._closed:
            self.ten_env.log_warn(
                "Callback is closed, will recreate connection..."
            )
            self.synthesizer = None

        # Ensure synthesizer exists, create if needed
        if self.synthesizer is None:
            self.ten_env.log_info(
                "Synthesizer is None, creating new one with existing callback"
            )

            # Reset callback cancel state for new request
            if self._callback:
                self._callback._cancelled = False
                self._callback._closed = False
                self.ten_env.log_info("Reset callback state for new request")

            self._create_synthesizer()

        # Start streaming TTS synthesis
        self.synthesizer.streaming_call(text)

    async def get_audio_data(self):
        """
        Get audio data from the queue. This is a separate method that can be called
        independently to consume audio data.
        Returns: (done, message_type, data)
        """
        return await self._receive_queue.get()

    def _duration_in_ms(self, start: datetime, end: datetime) -> int:
        """
        Calculate duration between two timestamps in milliseconds.

        Args:
            start: Start timestamp
            end: End timestamp

        Returns:
            Duration in milliseconds
        """
        return int((end - start).total_seconds() * 1000)

    def _duration_in_ms_since(self, start: datetime) -> int:
        """
        Calculate duration from a timestamp to now in milliseconds.

        Args:
            start: Start timestamp

        Returns:
            Duration in milliseconds from start to now
        """
        return self._duration_in_ms(start, datetime.now())

    def _get_audio_format(self):
        """
        Automatically generate AudioFormat based on configuration.

        Returns:
            AudioFormat: The appropriate audio format for the configuration
        """
        # Use local audio format
        if self.config.sample_rate in LOCAL_AUDIO_FORMAT_MAPPING:
            return LOCAL_AUDIO_FORMAT_MAPPING[self.config.sample_rate]
        self.ten_env.log_warn(
            f"Unsupported audio format: {self.config.sample_rate}Hz, using default format: PCM_16000HZ_MONO_16BIT"
        )
        return DEFAULT_LOCAL_AUDIO_FORMAT
