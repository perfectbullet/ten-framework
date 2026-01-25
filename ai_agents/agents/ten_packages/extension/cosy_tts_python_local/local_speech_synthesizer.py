# Copyright (c) Local CosyVoice Implementation
"""
Local CosyVoice WebSocket TTS Implementation
Based on the WebSocket interface documented in websocket_interface.md
"""
import json
import base64
import threading
from typing import Optional
from enum import Enum, unique
import websocket


class ResultCallback:
    """
    An interface that defines callback methods for getting speech synthesis results.
    Derive from this class and implement its function to provide your own data.
    """

    def on_open(self) -> None:
        pass

    def on_complete(self) -> None:
        pass

    def on_error(self, message) -> None:
        pass

    def on_close(self) -> None:
        pass

    def on_event(self, message: str) -> None:
        pass

    def on_data(self, data: bytes) -> None:
        pass


@unique
class AudioFormat(Enum):
    """Audio format enumeration matching the local service spec"""

    PCM_8000HZ_MONO_16BIT = ("pcm", 8000, "mono", 16)
    PCM_16000HZ_MONO_16BIT = ("pcm", 16000, "mono", 16)
    PCM_22050HZ_MONO_16BIT = ("pcm", 22050, "mono", 16)
    PCM_24000HZ_MONO_16BIT = ("pcm", 24000, "mono", 16)
    PCM_44100HZ_MONO_16BIT = ("pcm", 44100, "mono", 16)
    PCM_48000HZ_MONO_16BIT = ("pcm", 48000, "mono", 16)

    # Alias for default format
    DEFAULT = ("Default", 0, "0", 0)


class LocalSpeechSynthesizer:
    """Local CosyVoice TTS Client using WebSocket"""

    def __init__(
        self,
        model: str,
        voice: str,
        format: AudioFormat = AudioFormat.DEFAULT,
        volume: int = 50,
        speech_rate: float = 1.0,
        pitch_rate: float = 1.0,
        seed: int = 0,
        synthesis_type: int = 0,
        instruction: Optional[str] = None,
        language_hints: Optional[list] = None,
        headers: Optional[dict] = None,
        callback: Optional[ResultCallback] = None,
        workspace: Optional[str] = None,
        url: Optional[str] = None,
        additional_params: Optional[dict] = None,
    ):
        """
        Initialize local speech synthesizer

        Args:
            model: Model name (not used for local service, kept for compatibility)
            voice: Speaker ID (spk_id)
            format: Audio format
            url: WebSocket URL of local service
            callback: Callback for handling results
        """
        self.model = model
        self.voice = voice  # This will be used as spk_id
        self.format = format
        self.volume = volume
        self.speech_rate = speech_rate
        self.pitch_rate = pitch_rate
        self.callback = callback
        self.url = url or "ws://192.168.8.230:50002/streaming/ws"
        self.headers = headers or {}

        # WebSocket connection
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.connected = False
        self.connection_lock = threading.Lock()

        # Request tracking
        self.chunk_id = 0
        self.chunk_id_lock = threading.Lock()
        self.current_task_id: Optional[str] = None

        # State management
        self.is_cancelled = False
        self.is_closed = False

    def __connect(self, timeout_seconds: int = 5) -> None:
        """Establish WebSocket connection"""
        if self.connected:
            return

        with self.connection_lock:
            if self.connected:
                return

            self.ws = websocket.WebSocketApp(
                self.url,
                header=self.headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            # Start WebSocket in a separate thread
            # ping_interval > ping_timeout (required by websocket-client library)
            self.ws_thread = threading.Thread(
                target=lambda: self.ws.run_forever(
                    ping_interval=10,  # Send ping every 20 seconds
                    ping_timeout=5,   # Wait for pong response (must be < ping_interval)
                ),
                daemon=True
            )
            self.ws_thread.start()

            # Wait for connection
            for _ in range(timeout_seconds * 10):
                if self.connected:
                    return
                threading.Event().wait(0.1)

            if not self.connected:
                raise ConnectionError(
                    f"Failed to connect to {self.url} within {timeout_seconds}s"
                )

    def __is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self.connected and self.ws is not None

    def _on_open(self, ws):
        """WebSocket connection opened callback"""
        self.connected = True
        if self.callback:
            self.callback.on_open()

    def _on_message(self, ws, message):
        """WebSocket message received callback"""
        try:
            response = json.loads(message)
            msg_type = response.get("type")

            if msg_type == "audio":
                # Decode base64 audio data
                audio_b64 = response.get("data", "")
                audio_data = base64.b64decode(audio_b64)
                if self.callback and not self.is_cancelled:
                    self.callback.on_data(audio_data)

            elif msg_type == "complete":
                # Synthesis completed
                if self.callback and not self.is_cancelled:
                    self.callback.on_complete()

            elif msg_type == "error":
                # Error occurred
                error_msg = response.get("data", "Unknown error")
                if self.callback:
                    self.callback.on_error(error_msg)

        except json.JSONDecodeError as e:
            if self.callback:
                self.callback.on_error(f"Failed to parse response: {e}")
        except Exception as e:
            if self.callback:
                self.callback.on_error(f"Error processing message: {e}")

    def _on_error(self, ws, error):
        """WebSocket error callback"""
        if self.callback:
            self.callback.on_error(str(error))

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket closed callback"""
        self.connected = False
        if self.callback:
            self.callback.on_close()

    def __send_str(self, data: str):
        """Send string data through WebSocket"""
        if not self.__is_connected():
            raise ConnectionError("WebSocket is not connected")
        self.ws.send(data)

    def __get_next_chunk_id(self) -> int:
        """Get next chunk ID"""
        with self.chunk_id_lock:
            self.chunk_id += 1
            return self.chunk_id

    def streaming_call(self, text: str):
        """
        Streaming call to synthesize text

        Args:
            text: Text to synthesize
        """
        # Reset cancel state for new request
        self.is_cancelled = False
        self.is_closed = False

        if not self.__is_connected():
            self.__connect()

        # Prepare request according to websocket_interface.md
        chunk_id = self.__get_next_chunk_id()
        request = {
            "action": "synthesize",
            "text": text,
            "spk_id": self.voice,  # Use voice as speaker ID
            "chunk_id": chunk_id,
        }

        # Send request
        self.__send_str(json.dumps(request))
        self.current_task_id = str(chunk_id)

    def streaming_complete(self, complete_timeout_millis: int = 600000):
        """
        Wait for synthesis to complete

        Args:
            complete_timeout_millis: Timeout in milliseconds
        """
        # For local service, completion is signaled through callback
        # Just wait for a reasonable time
        timeout_seconds = complete_timeout_millis / 1000
        threading.Event().wait(timeout_seconds)

    def async_streaming_complete(self, complete_timeout_millis: int = 600000):
        """
        Signal completion of text input to server.
        Note: Does NOT close the connection - wait for server to send all audio.
        Connection will be closed when done=True is received or manually via close().

        Args:
            complete_timeout_millis: Timeout in milliseconds (not used, kept for compatibility)
        """
        # Do nothing - just keep connection open for audio response
        # Server will send complete signal when all audio is delivered
        pass

    def streaming_cancel(self):
        """Cancel current synthesis and close connection immediately"""
        self.is_cancelled = True
        if self.callback:
            # Notify callback that we're cancelling
            if hasattr(self.callback, "cancel"):
                self.callback.cancel()

        # Close connection immediately for cancel
        self.close()

    def close(self):
        """Close WebSocket connection (idempotent)"""
        if self.is_closed:
            return

        self.is_closed = True
        self.connected = False

        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass  # Ignore errors during close
            finally:
                self.ws = None

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)

    def reset(self):
        """Reset the synthesizer, close old connection and prepare for new one"""
        self.close()
        self.connected = False
        self.is_cancelled = False
        self.is_closed = False
        self.chunk_id = 0
        self.current_task_id = None
        self.ws = None
        self.ws_thread = None

    def get_last_request_id(self) -> Optional[str]:
        """Get the last request ID"""
        return self.current_task_id

    def call(self, text: str, timeout_millis: Optional[int] = None):
        """
        Synchronous call to synthesize text

        Args:
            text: Text to synthesize
            timeout_millis: Timeout in milliseconds
        """
        self.streaming_call(text)
        if timeout_millis:
            self.streaming_complete(timeout_millis)

    def get_response(self):
        """Get response (kept for compatibility)"""
        return None
