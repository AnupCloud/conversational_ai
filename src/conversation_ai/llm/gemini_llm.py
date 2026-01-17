"""
Google Gemini LLM integration for LiveKit agents.
Handles natural language understanding and response generation.
"""

import logging
import uuid
from typing import List, Optional

from google import genai
from livekit.agents import llm, APIConnectOptions

from ..config.settings import settings

logger = logging.getLogger(__name__)


class GeminiLLM(llm.LLM):
    """
    Custom LLM implementation using Google Gemini.
    Provides natural language understanding and generation for the conversational AI.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize Gemini LLM client.

        Args:
            api_key: Gemini API key (defaults to settings)
            model: Model name (defaults to settings)
            temperature: Sampling temperature (defaults to settings)
            max_tokens: Maximum tokens in response (defaults to settings)
        """
        super().__init__()

        # Model configuration
        self._model_name = model or settings.gemini_model
        self._temperature = temperature or settings.gemini_temperature
        self._max_tokens = max_tokens or settings.gemini_max_tokens
        self._api_key = api_key or settings.gemini_api_key

        # Initialize client with new API
        self._client = genai.Client(api_key=self._api_key)

        logger.info(f"Initialized Gemini LLM with model: {self._model_name}")

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: Optional[list] = None,
        conn_options: Optional[APIConnectOptions] = None,
        parallel_tool_calls: Optional[bool] = None,
        **kwargs
    ) -> "GeminiLLMStream":
        """
        Generate chat response using Gemini.

        Args:
            chat_ctx: Chat context with conversation history
            tools: Optional function tools
            conn_options: Connection options
            parallel_tool_calls: Whether to allow parallel tool calls
            **kwargs: Additional arguments (ignored)

        Returns:
            GeminiLLMStream - async context manager for streaming response
        """
        if conn_options is None:
            conn_options = APIConnectOptions()
        if tools is None:
            tools = []

        return GeminiLLMStream(
            llm=self,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            client=self._client,
        )

    def _build_contents(self, chat_ctx: llm.ChatContext) -> List[dict]:
        """
        Convert LiveKit ChatContext to Gemini contents format.

        Args:
            chat_ctx: LiveKit chat context

        Returns:
            List of content messages in Gemini format
        """
        contents = []
        system_instruction = None

        for item in chat_ctx.items:
            if not hasattr(item, 'role'):
                continue

            content = item.content if isinstance(item.content, str) else str(item.content)

            if item.role == "system":
                system_instruction = content
            elif item.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif item.role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })

        # Prepend system instruction as first user message if it exists
        if system_instruction:
            if contents:
                contents.insert(0, {
                    "role": "user",
                    "parts": [{"text": f"System instructions: {system_instruction}"}]
                })
            else:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System instructions: {system_instruction}"}]
                })

        return contents


class GeminiLLMStream(llm.LLMStream):
    """
    Stream wrapper for Gemini responses.
    Implements async context manager protocol for LiveKit agents.
    """

    def __init__(
        self,
        *,
        llm: GeminiLLM,
        chat_ctx: llm.ChatContext,
        tools: list,
        conn_options: APIConnectOptions,
        model_name: str,
        temperature: float,
        max_tokens: int,
        client: genai.Client,
    ):
        """
        Initialize stream with Gemini configuration.
        """
        super().__init__(
            llm=llm,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options
        )
        self._model_name = model_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = client
        self._response_text = None

    def _build_contents(self) -> List[dict]:
        """Build contents from chat context."""
        contents = []
        system_instruction = None

        for item in self._chat_ctx.items:
            if not hasattr(item, 'role'):
                continue

            content = item.content if isinstance(item.content, str) else str(item.content)

            if item.role == "system":
                system_instruction = content
            elif item.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif item.role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })

        if system_instruction:
            if contents:
                contents.insert(0, {
                    "role": "user",
                    "parts": [{"text": f"System instructions: {system_instruction}"}]
                })
            else:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System instructions: {system_instruction}"}]
                })

        return contents

    async def _run(self):
        """
        Run the LLM inference and emit chunks.
        """
        try:
            contents = self._build_contents()
            logger.debug(f"Sending {len(contents)} messages to Gemini")

            # Generate response using Gemini API
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=contents,
                config={
                    "temperature": self._temperature,
                    "max_output_tokens": self._max_tokens,
                }
            )

            self._response_text = response.text
            logger.debug(f"Gemini response: {self._response_text[:100]}...")

            # Emit the response as a chat chunk
            chunk = llm.ChatChunk(
                id=str(uuid.uuid4()),
                delta=llm.ChoiceDelta(
                    role="assistant",
                    content=self._response_text,
                )
            )

            self._event_ch.send_nowait(chunk)

        except Exception as e:
            logger.error(f"Error in Gemini chat generation: {e}", exc_info=True)
            raise
