"""
Sarvam AI Speech-to-Text (STT) integration for LiveKit agents.
Implements custom STT node using Sarvam AI's API.
"""

import asyncio
import logging
from typing import Optional

import aiohttp
from livekit.agents import stt, utils, APIConnectOptions

from ..config.settings import settings

logger = logging.getLogger(__name__)


class SarvamSTT(stt.STT):
    """
    Custom STT implementation using Sarvam AI.
    Integrates with LiveKit agents framework for real-time speech recognition.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        language: str = "hi-IN",  # Default to Hindi, can be changed
        sample_rate: int = 16000,
    ):
        """
        Initialize Sarvam STT client.

        Args:
            api_key: Sarvam API key (defaults to settings)
            api_url: Sarvam STT endpoint URL (defaults to settings)
            language: Language code for recognition (e.g., 'hi-IN', 'en-IN')
            sample_rate: Audio sample rate in Hz
        """
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )
        self._api_key = api_key or settings.sarvam_api_key
        self._api_url = api_url or settings.sarvam_stt_url
        self._language = language
        self._sample_rate = sample_rate
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is initialized."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _create_wav_header(self, pcm_data: bytes, sample_rate: int) -> bytes:
        """Create a WAV header for the PCM data."""
        import struct
        
        # WAV Header format
        # RIFF chunk
        header = b'RIFF'
        header += struct.pack('<I', 36 + len(pcm_data))  # ChunkSize
        header += b'WAVE'
        
        # fmt chunk
        header += b'fmt '
        header += struct.pack('<I', 16)  # Subchunk1Size (16 for PCM)
        header += struct.pack('<H', 1)   # AudioFormat (1 for PCM)
        header += struct.pack('<H', 1)   # NumChannels (1 for mono)
        header += struct.pack('<I', sample_rate)  # SampleRate
        header += struct.pack('<I', sample_rate * 2)  # ByteRate (SampleRate * NumChannels * BitsPerSample/8)
        header += struct.pack('<H', 2)   # BlockAlign (NumChannels * BitsPerSample/8)
        header += struct.pack('<H', 16)  # BitsPerSample (16)
        
        # data chunk
        header += b'data'
        header += struct.pack('<I', len(pcm_data))  # Subchunk2Size
        
        return header + pcm_data

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: Optional[str] = None,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """
        Recognize speech from audio buffer using Sarvam AI.

        Args:
            buffer: Audio buffer containing speech data
            language: Optional language override
            conn_options: API connection options

        Returns:
            SpeechEvent with recognized text
        """
        try:
            session = await self._ensure_session()

            # Convert audio buffer to bytes (raw PCM)
            pcm_data = buffer.data.tobytes()
            
            # Determine sample rate from buffer if available, otherwise use default
            current_sample_rate = getattr(buffer, 'sample_rate', self._sample_rate)
            
            # Add WAV header (required by Sarvam API)
            audio_data = self._create_wav_header(pcm_data, current_sample_rate)

            # Prepare request - Sarvam uses api-subscription-key header
            headers = {
                "api-subscription-key": self._api_key,
            }

            # Prepare form data for Sarvam STT API
            form_data = aiohttp.FormData()
            form_data.add_field(
                'file',
                audio_data,
                filename='audio.wav',
                content_type='audio/wav'
            )
            form_data.add_field('language_code', language or self._language)

            # Make API request to Sarvam AI
            logger.debug(
                f"Sending audio to Sarvam STT (size: {len(audio_data)} bytes, sample_rate: {current_sample_rate})"
            )

            async with session.post(
                self._api_url,
                headers=headers,
                data=form_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Sarvam STT API error: {response.status} - {error_text}"
                    )
                    return stt.SpeechEvent(
                        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[
                            stt.SpeechData(
                                language=self._language,
                                text="",
                                confidence=0.0,
                            )
                        ],
                    )

                result = await response.json()
                logger.debug(f"Sarvam STT response: {result}")

                # Extract transcript from response
                # Adjust based on actual Sarvam API response structure
                transcript = result.get("transcript", "")
                confidence = result.get("confidence", 1.0)

                return stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[
                        stt.SpeechData(
                            language=self._language,
                            text=transcript,
                            confidence=confidence,
                        )
                    ],
                )

        except asyncio.TimeoutError:
            logger.error("Sarvam STT request timed out")
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        language=self._language,
                        text="",
                        confidence=0.0,
                    )
                ],
            )
        except Exception as e:
            logger.error(f"Error in Sarvam STT recognition: {e}", exc_info=True)
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        language=self._language,
                        text="",
                        confidence=0.0,
                    )
                ],
            )

    async def aclose(self) -> None:
        """Clean up resources."""
        if self._session and not self._session.closed:
            await self._session.close()
