"""
Configuration management for the Conversational AI application.
Uses pydantic-settings for environment variable management.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Sarvam AI Configuration
    sarvam_api_key: str = Field(..., description="Sarvam AI API key")
    sarvam_stt_url: str = Field(
        default="https://api.sarvam.ai/speech-to-text",
        description="Sarvam AI STT endpoint URL",
    )
    sarvam_tts_url: str = Field(
        default="https://api.sarvam.ai/text-to-speech",
        description="Sarvam AI TTS endpoint URL",
    )
    sarvam_tts_speaker: str = Field(
        default="anushka",
        description="Sarvam TTS speaker voice (anushka, abhilash, manisha, vidya, arya, karun, hitesh)",
    )
    sarvam_tts_language: str = Field(
        default="en-IN", description="Sarvam TTS language code (e.g., en-IN, hi-IN)"
    )

    # Gemini API Configuration
    gemini_api_key: str = Field(..., description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-2.5-flash", description="Gemini model to use"
    )
    gemini_temperature: float = Field(
        default=0.7, description="Temperature for Gemini responses"
    )
    gemini_max_tokens: int = Field(
        default=1024, description="Maximum tokens for Gemini responses"
    )

    # LiveKit Configuration
    livekit_url: str = Field(
        default="ws://localhost:7880", description="LiveKit server URL"
    )
    livekit_api_key: str = Field(default="", description="LiveKit API key")
    livekit_api_secret: str = Field(default="", description="LiveKit API secret")

    # Conversation Settings
    max_conversation_history: int = Field(
        default=10, description="Maximum number of conversation turns to keep"
    )
    session_timeout: int = Field(
        default=300, description="Session timeout in seconds"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")


# Global settings instance
settings = Settings()
