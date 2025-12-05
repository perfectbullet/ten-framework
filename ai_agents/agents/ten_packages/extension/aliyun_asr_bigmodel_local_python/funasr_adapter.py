#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
FunASR Adapter - Provides Dashscope-compatible interface for local FunASR WebSocket service.

This adapter wraps the FunASR WebSocket client to provide the same interface as
Dashscope's Recognition SDK, enabling seamless switching between cloud and local ASR.
"""

import asyncio
import json
import ssl
import threading
import time
import traceback
from queue import Queue, Empty
from typing import Any, Dict, List, Optional, Union
from websocket import ABNF, create_connection


class FunASRRecognitionResult:
    """Adapter class compatible with Dashscope's RecognitionResult interface."""

    def __init__(self, message: Dict[str, Any]):
        """
        Initialize from FunASR WebSocket message.
        
        Args:
            message: Raw message from FunASR WebSocket
                Example interim: {'is_final': False, 'mode': '2pass-online', 'text': '家来', 'wav_name': 'default'}
                Example final: {'is_final': True, 'mode': '2pass-offline', 'stamp_sents': [...], 'text': '...', 'timestamp': '...', 'wav_name': 'default'}
        """
        self.raw_message = message
        self.status_code = 200  # Simulate HTTP OK status
        self.request_id = message.get("wav_name", "default")
        self.code = None
        self.message = ""
        
        # Build output structure compatible with Dashscope
        self.output = self._build_output(message)

    def _build_output(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert FunASR message to Dashscope-compatible output format."""
        text = message.get("text", "")
        mode = message.get("mode", "")
        is_final = message.get("is_final", False) or mode == "2pass-offline"
        
        # Build sentence structure
        sentence = {
            "text": text,
            "begin_time": 0,
            "end_time": 0,
            "words": []
        }
        
        # Extract timing information from stamp_sents if available (final results)
        if "stamp_sents" in message and message["stamp_sents"]:
            stamp_sent = message["stamp_sents"][0]  # Use first sentence
            sentence["begin_time"] = stamp_sent.get("start", 0)
            sentence["end_time"] = stamp_sent.get("end", 0)
            
            # Build words list with timestamps from ts_list
            text_seg = stamp_sent.get("text_seg", "")
            ts_list = stamp_sent.get("ts_list", [])
            
            if text_seg and ts_list:
                # Split text_seg by spaces to get individual words
                words_text = [w for w in text_seg.split() if w]
                
                # Match words with timestamps
                for i, word_text in enumerate(words_text):
                    if i < len(ts_list):
                        word_info = {
                            "text": word_text,
                            "begin_time": ts_list[i][0],
                            "end_time": ts_list[i][1]
                        }
                        sentence["words"].append(word_info)
        
        return {
            "sentence": sentence,
            "final": is_final
        }

    def get_sentence(self) -> Dict[str, Any]:
        """Get the sentence structure (compatible with Dashscope API)."""
        return self.output.get("sentence", {})

    @staticmethod
    def is_sentence_end(sentence: Dict[str, Any]) -> bool:
        """Check if this is the final result for a sentence."""
        # In FunASR, mode=='2pass-offline' or is_final==True indicates sentence end
        return sentence.get("final", False)

    def __str__(self):
        return json.dumps(self.output, ensure_ascii=False)


class FunASRRecognitionCallback:
    """Base callback class compatible with Dashscope's RecognitionCallback interface."""

    def on_open(self) -> None:
        """Called when WebSocket connection is established."""
        pass

    def on_complete(self) -> None:
        """Called when recognition is completed."""
        pass

    def on_error(self, result: FunASRRecognitionResult) -> None:
        """Called when an error occurs."""
        pass

    def on_close(self) -> None:
        """Called when WebSocket connection is closed."""
        pass

    def on_event(self, result: FunASRRecognitionResult) -> None:
        """Called when a recognition result is received."""
        pass


class FunASRRecognition:
    """
    FunASR WebSocket Recognition client with Dashscope-compatible interface.
    
    This class adapts the FunASR WebSocket API to match Dashscope's Recognition interface,
    enabling drop-in replacement in the TEN Framework extension.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: str = "10095",
        is_ssl: bool = False,
        chunk_size: str = "5,10,5",
        chunk_interval: int = 10,
        mode: str = "2pass",
        wav_name: str = "default",
        callback: Optional[FunASRRecognitionCallback] = None,
        # Dashscope-compatible parameters (may not all be used by FunASR)
        model: str = "",
        format: str = "pcm",
        sample_rate: int = 16000,
        language_hints: List[str] = None,
        **kwargs
    ):
        """
        Initialize FunASR WebSocket recognition client.
        
        Args:
            host: FunASR server host
            port: FunASR server port
            is_ssl: Whether to use WSS (True) or WS (False)
            chunk_size: FunASR chunk size parameter (e.g., "5,10,5")
            chunk_interval: Chunk interval in milliseconds
            mode: Recognition mode ("2pass", "offline", "online")
            wav_name: Audio stream identifier
            callback: Callback handler for recognition events
            model: Model name (for compatibility, not used by FunASR directly)
            format: Audio format (default: "pcm")
            sample_rate: Audio sample rate (default: 16000)
            language_hints: Language hints (for compatibility)
            **kwargs: Additional parameters (hotwords, itn, etc.)
        """
        self.host = host
        self.port = port
        self.is_ssl = is_ssl
        self.chunk_size = chunk_size
        self.chunk_interval = chunk_interval
        self.mode = mode
        self.wav_name = wav_name
        self.callback = callback
        self.sample_rate = sample_rate
        self.format = format
        self.kwargs = kwargs
        
        # Connection state
        self.websocket = None
        self._running = False
        self._thread_recv = None
        self.msg_queue = Queue()
        
        # Asyncio event loop for thread-safe callbacks
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread
            pass

    def start(self, **kwargs) -> None:
        """
        Start WebSocket connection and recognition (compatible with Dashscope API).
        
        Args:
            **kwargs: Additional parameters to override initialization values
        """
        if self._running:
            raise RuntimeError("Recognition is already running")
        
        # Update parameters if provided
        self.kwargs.update(kwargs)
        
        try:
            # Build WebSocket URI
            protocol = "wss" if self.is_ssl else "ws"
            uri = f"{protocol}://{self.host}:{self.port}"
            
            # Create SSL context for WSS
            if self.is_ssl:
                ssl_context = ssl.SSLContext()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_opt = {"cert_reqs": ssl.CERT_NONE}
            else:
                ssl_context = None
                ssl_opt = None
            
            # Establish WebSocket connection
            self.websocket = create_connection(uri, sslopt=ssl_opt, ssl=ssl_context)
            self._running = True
            
            # Start message receiving thread
            self._thread_recv = threading.Thread(target=self._thread_receive_messages, daemon=True)
            self._thread_recv.start()
            
            # Send initialization message
            chunk_size_list = [int(x) for x in self.chunk_size.split(",")]
            init_message = {
                "mode": self.mode,
                "chunk_size": chunk_size_list,
                "chunk_interval": self.chunk_interval,
                "wav_name": self.wav_name,
                "is_speaking": True,
                "itn": self.kwargs.get("itn", True),
            }
            
            # Add hotwords if provided
            if "hotwords" in self.kwargs:
                init_message["hotwords"] = self.kwargs["hotwords"]
            
            # Add other FunASR-specific parameters
            for key in ["encoder_chunk_look_back", "decoder_chunk_look_back"]:
                if key in self.kwargs:
                    init_message[key] = self.kwargs[key]
            
            self.websocket.send(json.dumps(init_message))
            
            # Trigger on_open callback
            if self.callback:
                self._safe_callback(self.callback.on_open)
            
        except Exception as e:
            self._running = False
            error_result = FunASRRecognitionResult({
                "text": "",
                "error": str(e),
                "is_final": False
            })
            error_result.status_code = 500
            error_result.message = f"Failed to connect to FunASR server: {e}"
            
            if self.callback:
                self._safe_callback(self.callback.on_error, error_result)
            raise

    def _thread_receive_messages(self) -> None:
        """Background thread to receive WebSocket messages and trigger callbacks."""
        try:
            while self._running:
                try:
                    msg = self.websocket.recv()
                    if msg is None or len(msg) == 0:
                        continue
                    
                    # Parse JSON message
                    msg_dict = json.loads(msg)
                    result = FunASRRecognitionResult(msg_dict)
                    
                    # Queue the message for potential synchronous access
                    self.msg_queue.put(msg_dict)
                    
                    # Trigger on_event callback
                    if self.callback:
                        self._safe_callback(self.callback.on_event, result)
                    
                except Exception as e:
                    if self._running:
                        # Only report errors if we're still supposed to be running
                        error_result = FunASRRecognitionResult({
                            "text": "",
                            "error": str(e),
                            "is_final": False
                        })
                        error_result.status_code = 500
                        error_result.message = f"Error receiving message: {e}"
                        
                        if self.callback:
                            self._safe_callback(self.callback.on_error, error_result)
                    break
        finally:
            # Connection closed
            if self.callback:
                self._safe_callback(self.callback.on_close)

    def _safe_callback(self, callback_func, *args) -> None:
        """
        Safely invoke callback function in asyncio event loop context.
        
        This ensures thread-safe callback execution when callbacks are coroutines
        or need to interact with asyncio-based code.
        """
        if self.loop and self.loop.is_running():
            # If we have an event loop, schedule the callback there
            if asyncio.iscoroutinefunction(callback_func):
                asyncio.run_coroutine_threadsafe(callback_func(*args), self.loop)
            else:
                self.loop.call_soon_threadsafe(callback_func, *args)
        else:
            # No event loop or not running, call directly
            callback_func(*args)

    def send_audio_frame(self, audio_data: bytes) -> None:
        """
        Send audio frame to FunASR server (compatible with Dashscope API).
        
        Args:
            audio_data: Raw audio bytes (PCM format)
        """
        if not self._running or not self.websocket:
            raise RuntimeError("Recognition is not running")
        
        try:
            self.websocket.send(audio_data, ABNF.OPCODE_BINARY)
        except Exception as e:
            error_result = FunASRRecognitionResult({
                "text": "",
                "error": str(e),
                "is_final": False
            })
            error_result.status_code = 500
            error_result.message = f"Error sending audio frame: {e}"
            
            if self.callback:
                self._safe_callback(self.callback.on_error, error_result)
            raise

    def stop(self, timeout: float = 1.0) -> None:
        """
        Stop recognition and close WebSocket connection (compatible with Dashscope API).
        
        Args:
            timeout: Time to wait for final results before closing
        """
        if not self._running:
            return
        
        try:
            # Send end-of-speech message
            if self.websocket:
                end_message = json.dumps({"is_speaking": False})
                self.websocket.send(end_message)
                
                # Wait for final results
                time.sleep(timeout)
                
                # Close WebSocket
                self.websocket.close()
        except Exception as e:
            # Log error but continue cleanup
            pass
        finally:
            self._running = False
            self.websocket = None
            
            # Trigger on_complete callback
            if self.callback:
                self._safe_callback(self.callback.on_complete)

    def is_running(self) -> bool:
        """Check if recognition is currently running."""
        return self._running

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get the last message from queue (for synchronous usage patterns)."""
        try:
            return self.msg_queue.get_nowait()
        except Empty:
            return None
