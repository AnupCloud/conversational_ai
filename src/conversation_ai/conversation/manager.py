"""
Conversation management for multi-turn dialogue.
Handles context preservation, history tracking, and session management.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4

from livekit.agents import llm

from ..config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """Represents a single turn in the conversation."""

    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ConversationSession:
    """Represents a conversation session with full context."""

    session_id: str
    history: deque = field(default_factory=deque)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """
        Add a conversation turn to the history.

        Args:
            role: Role of the speaker (user/assistant/system)
            content: Content of the message
            metadata: Optional metadata for the turn
        """
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.history.append(turn)
        self.last_activity = time.time()

        # Limit history size
        max_history = settings.max_conversation_history
        if len(self.history) > max_history * 2:  # Keep user+assistant pairs
            # Remove oldest turns while keeping pairs
            self.history.popleft()
            self.history.popleft()

        logger.debug(
            f"Session {self.session_id}: Added {role} turn, "
            f"history size: {len(self.history)}"
        )

    def get_history(self, max_turns: Optional[int] = None) -> List[ConversationTurn]:
        """
        Get conversation history.

        Args:
            max_turns: Maximum number of turns to return

        Returns:
            List of conversation turns
        """
        if max_turns is None:
            return list(self.history)
        return list(self.history)[-max_turns:]

    def is_expired(self) -> bool:
        """Check if session has expired based on inactivity."""
        timeout = settings.session_timeout
        return (time.time() - self.last_activity) > timeout

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        logger.info(f"Session {self.session_id}: History cleared")


class ConversationManager:
    """
    Manages multiple conversation sessions and context.
    Provides utilities for building chat contexts for LLM.
    """

    def __init__(self):
        """Initialize conversation manager."""
        self._sessions: Dict[str, ConversationSession] = {}
        self._system_prompt = self._build_system_prompt()
        logger.info("Conversation manager initialized")

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for the conversational AI.

        Returns:
            System prompt string
        """
        return """You are a helpful, friendly, and knowledgeable AI assistant engaged in a natural conversation.
Your role is to:
- Understand user intent and respond appropriately
- Maintain context across multiple turns of conversation
- Ask clarifying questions when needed
- Provide accurate and helpful information
- Be conversational and engaging while remaining professional
- Remember previous turns in the conversation and reference them when relevant

Guidelines:
- Keep responses concise but informative
- Use natural, conversational language
- Show empathy and understanding
- If you don't know something, say so honestly
- Help users accomplish their goals effectively
"""

    def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new conversation session.

        Args:
            session_id: Optional custom session ID

        Returns:
            Session ID
        """
        if session_id is None:
            session_id = str(uuid4())

        session = ConversationSession(session_id=session_id)
        self._sessions[session_id] = session

        logger.info(f"Created new session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """
        Get conversation session by ID.

        Args:
            session_id: Session identifier

        Returns:
            ConversationSession or None if not found
        """
        session = self._sessions.get(session_id)

        # Check if session is expired
        if session and session.is_expired():
            logger.info(f"Session {session_id} expired, removing")
            del self._sessions[session_id]
            return None

        return session

    def add_user_message(
        self, session_id: str, content: str, metadata: Optional[Dict] = None
    ) -> None:
        """
        Add user message to session.

        Args:
            session_id: Session identifier
            content: Message content
            metadata: Optional metadata
        """
        session = self.get_session(session_id)
        if session:
            session.add_turn("user", content, metadata)
        else:
            logger.warning(f"Session {session_id} not found")

    def add_assistant_message(
        self, session_id: str, content: str, metadata: Optional[Dict] = None
    ) -> None:
        """
        Add assistant message to session.

        Args:
            session_id: Session identifier
            content: Message content
            metadata: Optional metadata
        """
        session = self.get_session(session_id)
        if session:
            session.add_turn("assistant", content, metadata)
        else:
            logger.warning(f"Session {session_id} not found")

    def build_chat_context(self, session_id: str) -> llm.ChatContext:
        """
        Build LiveKit ChatContext from session history.

        Args:
            session_id: Session identifier

        Returns:
            ChatContext for LLM
        """
        chat_ctx = llm.ChatContext()

        # Add system prompt
        chat_ctx.add_message(
            role="system",
            content=self._system_prompt,
        )

        # Add conversation history
        session = self.get_session(session_id)
        if session:
            for turn in session.get_history():
                role = "user" if turn.role == "user" else "assistant"
                chat_ctx.add_message(
                    role=role,
                    content=turn.content,
                )

        return chat_ctx

    def clear_session(self, session_id: str) -> None:
        """
        Clear a conversation session.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Cleared session: {session_id}")

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns:
            Number of sessions removed
        """
        expired = [
            sid for sid, session in self._sessions.items() if session.is_expired()
        ]

        for sid in expired:
            del self._sessions[sid]
            logger.info(f"Removed expired session: {sid}")

        return len(expired)

    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self._sessions)


# Global conversation manager instance
conversation_manager = ConversationManager()
