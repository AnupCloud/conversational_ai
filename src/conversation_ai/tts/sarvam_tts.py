"""
Sarvam AI Text-to-Speech (TTS) integration for LiveKit agents.
Implements custom TTS using Sarvam AI's Bulbul v2 API.
"""

import asyncio
import base64
import logging
from typing import Optional

import aiohttp
from livekit.agents import tts, APIConnectOptions

from ..config.settings import settings

logger = logging.getLogger(__name__)


class SarvamChunkedStream(tts.ChunkedStream):
    """Custom ChunkedStream implementation for Sarvam TTS."""

    def __init__(
        self,
        *,
        tts_instance: "SarvamTTS",
        input_text: str,
        conn_options: APIConnectOptions,
    ):
        super().__init__(
            tts=tts_instance,
            input_text=input_text,
            conn_options=conn_options,
        )
        self._tts_instance = tts_instance

    async def _run(self, output_emitter) -> None:
        """Run the TTS synthesis and emit audio events.

        Args:
            output_emitter: AudioEmitter from the base class (managed by framework)
        """
        try:
            # Get raw audio data from Sarvam TTS
            request_id, pcm_data = await self._tts_instance._synthesize_raw_audio(self._input_text)

            # Initialize the emitter with audio parameters
            output_emitter.initialize(
                request_id=request_id,
                sample_rate=self._tts_instance._sample_rate,
                num_channels=1,
                mime_type="audio/pcm",
            )

            # Push the PCM audio data
            output_emitter.push(pcm_data)
            logger.debug(f"Pushed {len(pcm_data)} bytes of PCM audio to emitter")

            # Flush the buffer and signal end of input
            output_emitter.flush()
            output_emitter.end_input()
            logger.debug("Audio emitter flushed and input ended")

        except Exception as e:
            logger.error(f"Error in TTS stream: {e}", exc_info=True)
            raise


class SarvamTTS(tts.TTS):
    """
    Custom TTS implementation using Sarvam AI Bulbul v2.
    Integrates with LiveKit agents framework for natural voice synthesis.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_url: str = "https://api.sarvam.ai/text-to-speech",
        language: str = "en-IN",
        speaker: str = "anushka",
        pitch: float = 0.0,
        pace: float = 1.0,
        loudness: float = 1.5,
        sample_rate: int = 24000,
    ):
        """
        Initialize Sarvam TTS client.

        Args:
            api_key: Sarvam API key (defaults to settings)
            api_url: Sarvam TTS endpoint URL
            language: Language code (e.g., 'en-IN', 'hi-IN', 'ta-IN')
            speaker: Voice name (anushka, abhilash, manisha, vidya, arya, karun, hitesh)
            pitch: Voice pitch (-0.75 to 0.75)
            pace: Speech speed (0.5 to 2.0)
            loudness: Volume (0.3 to 3.0)
            sample_rate: Audio sample rate (8000, 16000, 22050, or 24000 Hz)
        """
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=1,
        )

        self._api_key = api_key or settings.sarvam_api_key
        self._api_url = api_url
        self._language = language
        self._speaker = speaker
        self._pitch = max(-0.75, min(0.75, pitch))
        self._pace = max(0.5, min(2.0, pace))
        self._loudness = max(0.3, min(3.0, loudness))
        self._sample_rate = sample_rate
        self._session: Optional[aiohttp.ClientSession] = None

        logger.info(
            f"Initialized Sarvam TTS with speaker: {speaker}, "
            f"language: {language}, sample_rate: {sample_rate}"
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is initialized."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def synthesize(
        self,
        text: str,
        *,
        conn_options: Optional[APIConnectOptions] = None,
    ) -> SarvamChunkedStream:
        """
        Public synthesize method required by TTS base class.

        Args:
            text: Text to synthesize
            conn_options: Connection options (optional)

        Returns:
            SarvamChunkedStream with audio data
        """
        if conn_options is None:
            conn_options = APIConnectOptions()

        return SarvamChunkedStream(
            tts_instance=self,
            input_text=text,
            conn_options=conn_options,
        )

    async def _synthesize_raw_audio(self, text: str) -> tuple[str, bytes]:
        """
        Synthesize raw PCM audio from text using Sarvam AI.

        Args:
            text: Text to convert to speech

        Returns:
            Tuple of (request_id, pcm_data)
        """
        try:
            session = await self._ensure_session()

            # Prepare request
            headers = {
                "Content-Type": "application/json",
                "api-subscription-key": self._api_key,
            }

            payload = {
                "text": text[:1500],  # Max 1500 characters
                "target_language_code": self._language,
                "speaker": self._speaker,
                "pitch": self._pitch,
                "pace": self._pace,
                "loudness": self._loudness,
                "speech_sample_rate": self._sample_rate,
                "output_audio_codec": "wav",
                "model": "bulbul:v2",
            }

            logger.debug(
                f"Sending text to Sarvam TTS (length: {len(text)} chars, "
                f"speaker: {self._speaker})"
            )

            # Make API request
            async with session.post(
                self._api_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Sarvam TTS API error: {response.status} - {error_text}"
                    )
                    raise Exception(f"Sarvam TTS API error: {response.status}")

                result = await response.json()
                request_id = result.get("request_id", "sarvam-tts")
                logger.debug("Received TTS response from Sarvam AI")

                # Extract and decode audio
                if "audios" in result and len(result["audios"]) > 0:
                    # Sarvam returns base64-encoded audio
                    audio_base64 = result["audios"][0]
                    audio_data = base64.b64decode(audio_base64)

                    logger.info(
                        f"Generated audio: {len(audio_data)} bytes, "
                        f"sample_rate: {self._sample_rate}"
                    )

                    # For WAV format, skip the 44-byte header to get raw PCM
                    if len(audio_data) > 44:
                        pcm_data = audio_data[44:]  # Skip WAV header
                        return request_id, pcm_data
                    else:
                        logger.warning("Received audio data is too small")
                        return request_id, b""

                return request_id, b""

        except asyncio.TimeoutError:
            logger.error("Sarvam TTS request timed out")
            raise
        except Exception as e:
            logger.error(f"Error in Sarvam TTS synthesis: {e}", exc_info=True)
            raise

    async def aclose(self) -> None:
        """Clean up resources."""
        if self._session and not self._session.closed:
            await self._session.close()

    def update_options(
        self,
        *,
        speaker: Optional[str] = None,
        pitch: Optional[float] = None,
        pace: Optional[float] = None,
        loudness: Optional[float] = None,
    ) -> None:
        """
        Update TTS options dynamically.

        Args:
            speaker: Voice name
            pitch: Voice pitch
            pace: Speech speed
            loudness: Volume
        """
        if speaker is not None:
            self._speaker = speaker
            logger.info(f"Updated speaker to: {speaker}")

        if pitch is not None:
            self._pitch = max(-0.75, min(0.75, pitch))
            logger.info(f"Updated pitch to: {self._pitch}")

        if pace is not None:
            self._pace = max(0.5, min(2.0, pace))
            logger.info(f"Updated pace to: {self._pace}")

        if loudness is not None:
            self._loudness = max(0.3, min(3.0, loudness))
            logger.info(f"Updated loudness to: {self._loudness}")
