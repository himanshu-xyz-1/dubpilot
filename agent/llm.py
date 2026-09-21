# Unified LLM provider supporting both Groq Cloud (ultra-fast 500+ tokens/sec)
# and local Ollama LLaMA models with multi-turn session memory and async streaming.

from __future__ import annotations
import json
import logging
import os
import time
from typing import AsyncIterator, Dict, List, Optional
import httpx

logger = logging.getLogger("dubpilot.llm")


def load_env_file():
    """Lightweight .env loader without external dependencies."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except Exception:
            pass


load_env_file()


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


class GroqLLM:
    """
    Groq Cloud client running high-performance LPU models at 500+ tokens/sec.
    """

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key.strip()
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.base_url = "https://api.groq.com/openai/v1"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("gsk_"))

    def generate(self, messages: List[Dict[str, str]], system_prompt: str = "") -> Optional[str]:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
                logger.warning(f"Groq API error {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Groq generation exception: {e}")
        return None

    async def stream_chat(
        self, messages: List[Dict[str, str]], system_prompt: str = ""
    ) -> AsyncIterator[str]:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Groq stream error: {response.status_code}")
                    return
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            continue


class OllamaLLM:
    """
    Local Ollama client running local models (e.g. LLaMA 3.2 3B).
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

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name", "") for m in res.json().get("models", [])]
                    return any(self.model in m or m.startswith(self.model.split(":")[0]) for m in models)
        except Exception:
            return False
        return False

    def generate(self, messages: List[Dict[str, str]], system_prompt: str = "") -> Optional[str]:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code == 200:
                    return res.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"Ollama generation error: {e}")
        return None

    async def stream_chat(
        self, messages: List[Dict[str, str]], system_prompt: str = ""
    ) -> AsyncIterator[str]:
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
            "options": {"temperature": 0.2},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code != 200:
                    return
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue


class UnifiedLLM:
    """
    Intelligent LLM router:
    1. Uses Groq Cloud (500+ tokens/sec, 120B model) when GROQ_API_KEY is present.
    2. Falls back to local Ollama (LLaMA 3.2) when offline or key is missing.
    3. Manages conversational memory across turns.
    4. Includes State Manipulator for chaos testing and fallback verification.
    """

    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY", "")
        self.groq = GroqLLM(api_key=groq_key) if groq_key else None
        self.ollama = OllamaLLM()
        self.memory = SessionMemory()

        # State Manipulator simulation flags
        self.simulate_groq_failure: bool = False
        self.simulate_ollama_failure: bool = False

    def set_simulation_state(self, groq_failure: Optional[bool] = None, ollama_failure: Optional[bool] = None):
        """Allows testing fallback by deliberately simulating API or local model outages."""
        if groq_failure is not None:
            self.simulate_groq_failure = groq_failure
            logger.info(f"[STATE MANIPULATOR] Groq failure simulation set to: {groq_failure}")
        if ollama_failure is not None:
            self.simulate_ollama_failure = ollama_failure
            logger.info(f"[STATE MANIPULATOR] Ollama failure simulation set to: {ollama_failure}")

    def get_simulation_state(self) -> Dict[str, any]:
        """Returns the active provider and simulation flags."""
        return {
            "simulate_groq_failure": self.simulate_groq_failure,
            "simulate_ollama_failure": self.simulate_ollama_failure,
            "active_provider": self.get_active_provider(),
            "active_model": self.get_model_name(),
            "groq_configured": bool(self.groq and self.groq.is_available()),
            "ollama_online": self.ollama.is_available(),
        }

    def get_active_provider(self):
        if not self.simulate_groq_failure and self.groq and self.groq.is_available():
            return "groq"
        if not self.simulate_ollama_failure and self.ollama and self.ollama.is_available():
            return "ollama"
        return "none"

    def get_model_name(self) -> str:
        provider = self.get_active_provider()
        if provider == "groq":
            return f"groq ({self.groq.model})"
        if provider == "ollama":
            suffix = " [FALLBACK]" if self.simulate_groq_failure else ""
            return f"ollama ({self.ollama.model}){suffix}"
        return "deterministic_kb"

    def is_available(self) -> bool:
        return self.get_active_provider() != "none"

    def generate(self, messages: List[Dict[str, str]], system_prompt: str = "") -> Optional[str]:
        # 1. Try Groq if not simulated as failed
        if not self.simulate_groq_failure and self.groq and self.groq.is_available():
            ans = self.groq.generate(messages, system_prompt=system_prompt)
            if ans:
                return ans
            logger.warning("[FALLBACK TRIGGERED] Groq returned empty, routing to Ollama...")

        # 2. Fallback to local Ollama if not simulated as failed
        if not self.simulate_ollama_failure and self.ollama and self.ollama.is_available():
            return self.ollama.generate(messages, system_prompt=system_prompt)

        return None

    async def stream_chat(
        self, messages: List[Dict[str, str]], system_prompt: str = ""
    ) -> AsyncIterator[str]:
        # 1. Stream from Groq if not simulated as failed
        if not self.simulate_groq_failure and self.groq and self.groq.is_available():
            success = False
            async for token in self.groq.stream_chat(messages, system_prompt=system_prompt):
                success = True
                yield token
            if success:
                return
            logger.warning("[FALLBACK TRIGGERED] Groq stream failed, routing to Ollama...")

        # 2. Fallback to local Ollama if not simulated as failed
        if not self.simulate_ollama_failure and self.ollama and self.ollama.is_available():
            async for token in self.ollama.stream_chat(messages, system_prompt=system_prompt):
                yield token
