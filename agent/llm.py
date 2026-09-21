# Interface to local Ollama instance running LLaMA models.
# Handles connection health checks, multi-turn chat memory, and async token streaming.

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Dict, List, Optional
import httpx

logger = logging.getLogger("dubpilot.llm")


class SessionMemory:
    """
    Stores recent chat history per session for multi-turn conversations.
    Automatically expires old conversations after 2 hours.
    """

    def __init__(self, ttl_seconds: int = 7200, max_turns: int = 10):
        self.ttl = ttl_seconds
        self.max_turns = max_turns
        self.sessions: Dict[str, Dict[str, any]] = {}

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        if not session_id or session_id not in self.sessions:
            return []
        session = self.sessions[session_id]
        if time.time() - session["last_active"] > self.ttl:
            del self.sessions[session_id]
            return []
        return session["messages"]

    def add_turn(self, session_id: str, user_text: str, assistant_text: str):
        if not session_id:
            return
        now = time.time()
        if session_id not in self.sessions:
            self.sessions[session_id] = {"last_active": now, "messages": []}
        
        entry = self.sessions[session_id]
        entry["last_active"] = now
        entry["messages"].append({"role": "user", "content": user_text})
        entry["messages"].append({"role": "assistant", "content": assistant_text})

        # Keep history within limit
        if len(entry["messages"]) > self.max_turns * 2:
            entry["messages"] = entry["messages"][-self.max_turns * 2:]


class OllamaLLM:
    """
    Client for interacting with local Ollama LLaMA models.
    Supports streaming and graceful fallback if Ollama is offline.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.timeout = timeout
        self.memory = SessionMemory()

    def is_available(self) -> bool:
        """Quick check to see if Ollama server and model are ready."""
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name", "") for m in res.json().get("models", [])]
                    # Check if our target model or its base name is pulled
                    return any(self.model in m or m.startswith(self.model.split(":")[0]) for m in models)
        except Exception:
            return False
        return False

    def generate(self, messages: List[Dict[str, str]], system_prompt: str = "") -> Optional[str]:
        """
        Synchronous completion call using LLaMA.
        Returns the text response, or None if Ollama fails.
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"Ollama generation error: {e}")
            return None
        return None

    async def stream_chat(
        self, messages: List[Dict[str, str]], system_prompt: str = ""
    ) -> AsyncIterator[str]:
        """
        Asynchronously streams tokens from LLaMA as they are generated.
        Yields raw string chunks.
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code != 200:
                    logger.error(f"Ollama stream failed with status {response.status_code}")
                    return
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
