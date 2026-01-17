"""
Main Voice Agent implementation using ottomator pattern.
Orchestrates the STT-LLM-TTS pipeline for conversational AI.
"""

import logging
import os
from typing import Optional

from livekit import agents
from livekit.agents import Agent, AgentSession, RunContext, room_io
from livekit.agents.llm import function_tool
from livekit.plugins import silero

from ..config.settings import settings
from ..conversation.manager import conversation_manager
from ..llm.gemini_llm import GeminiLLM
from ..stt.sarvam_stt import SarvamSTT
from ..tts.sarvam_tts import SarvamTTS

logger = logging.getLogger(__name__)


class ConversationalAssistant(Agent):
    """
    Conversational AI Assistant using Agent pattern from ottomator.
    Manages multi-turn conversations with Sarvam STT, Gemini LLM, and Sarvam TTS.
    """

    def __init__(self):
        """Initialize the conversational assistant."""
        super().__init__(
            instructions=conversation_manager._system_prompt
        )
        self.session_id: Optional[str] = None
        logger.info("Conversational Assistant initialized")

    async def on_enter(self):
        """
        Called when agent enters a session.
        Sets up conversation session and greets the user.
        """
        # Create a new conversation session
        self.session_id = conversation_manager.create_session()
        logger.info(f"Created conversation session: {self.session_id}")

        # Generate initial greeting
        await self.session.generate_reply(
            instructions="Greet the user warmly and ask how you can help them today."
        )

    async def on_exit(self):
        """
        Called when agent exits a session.
        Cleans up conversation session.
        """
        if self.session_id:
            logger.info(f"Ending conversation session: {self.session_id}")
            # Optionally clear the session
            # conversation_manager.clear_session(self.session_id)

    @function_tool
    async def get_conversation_summary(self, context: RunContext) -> str:
        """
        Get a summary of the current conversation.
        Useful for the agent to reference what has been discussed.
        """
        if not self.session_id:
            return "No active conversation session."

        session = conversation_manager.get_session(self.session_id)
        if not session:
            return "Session not found."

        history = session.get_history()
        if not history:
            return "No conversation history yet."

        summary_parts = []
        for turn in history[-5:]:  # Last 5 turns
            summary_parts.append(f"{turn.role}: {turn.content[:100]}...")

        return "Recent conversation:\n" + "\n".join(summary_parts)

    @function_tool
    async def remember_context(
        self,
        context: RunContext,
        key: str,
        value: str
    ) -> str:
        """
        Remember a piece of context for later use in the conversation.

        Args:
            key: The key to store the context under
            value: The value to remember
        """
        if self.session_id:
            session = conversation_manager.get_session(self.session_id)
            if session:
                session.metadata[key] = value
                return f"Remembered: {key} = {value}"
        return "Could not save context."

    @function_tool
    async def recall_context(self, context: RunContext, key: str) -> str:
        """
        Recall a previously remembered piece of context.

        Args:
            key: The key to recall
        """
        if self.session_id:
            session = conversation_manager.get_session(self.session_id)
            if session and key in session.metadata:
                return f"{key}: {session.metadata[key]}"
        return f"No context found for key: {key}"


def prewarm(proc: agents.JobProcess):
    """
    Prewarm function to initialize VAD model before processing.
    This reduces latency on first voice detection.
    """
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model prewarmed")


async def entrypoint(ctx: agents.JobContext):
    """
    Main entrypoint for the LiveKit agent.
    Sets up the voice pipeline with Sarvam STT, Gemini LLM, and Sarvam TTS.
    """
    logger.info(f"Starting agent for room: {ctx.room.name}")

    # Connect to the room first
    await ctx.connect()
    logger.info("Connected to room")

    # Wait for a participant to join (important for input binding)
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant ready: {participant.identity}")

    # Initialize components
    stt = SarvamSTT(language="en-IN")
    llm = GeminiLLM()
    tts = SarvamTTS(
        language=settings.sarvam_tts_language,
        speaker=settings.sarvam_tts_speaker,
    )

    # Get prewarmed VAD or load new one
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        vad = silero.VAD.load(
            min_speech_duration=0.1,
            min_silence_duration=0.5,
            prefix_padding_duration=0.1,
        )

    logger.info("Voice pipeline components initialized")
    logger.info(f"  - STT: Sarvam AI")
    logger.info(f"  - LLM: Gemini ({settings.gemini_model})")
    logger.info(f"  - TTS: Sarvam AI ({settings.sarvam_tts_speaker})")

    # Create and start the agent session
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
    )

    # Configure room options with proper audio input bound to the participant
    room_options = room_io.RoomOptions(
        audio_input=room_io.AudioInputOptions(
            sample_rate=16000,  # Match STT sample rate
            num_channels=1,
        ),
        audio_output=room_io.AudioOutputOptions(
            sample_rate=24000,  # Match TTS sample rate
            num_channels=1,
        ),
        participant_identity=participant.identity,  # Bind to specific participant
    )

    # Start the session with our conversational assistant
    await session.start(
        room=ctx.room,
        agent=ConversationalAssistant(),
        room_options=room_options,
    )

    logger.info("Agent session started and ready")


def main():
    """Main entry point for running the agent."""
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting Conversational AI Agent")
    logger.info(f"Using Gemini model: {settings.gemini_model}")
    logger.info(f"Using Sarvam STT API")

    # LiveKit CLI expects credentials from environment variables or command line
    if settings.livekit_url:
        os.environ["LIVEKIT_URL"] = settings.livekit_url
        logger.info(f"LiveKit URL: {settings.livekit_url}")

    if settings.livekit_api_key:
        os.environ["LIVEKIT_API_KEY"] = settings.livekit_api_key
        logger.info("LiveKit API Key: configured")

    if settings.livekit_api_secret:
        os.environ["LIVEKIT_API_SECRET"] = settings.livekit_api_secret
        logger.info("LiveKit API Secret: configured")

    # Run the agent with LiveKit CLI
    # Using auto-dispatch (no agent_name) - agent joins when any participant connects
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )


if __name__ == "__main__":
    main()
