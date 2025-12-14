from __future__ import annotations

from dataclasses import dataclass

from google import genai


@dataclass(frozen=True)
class GeminiClient:
    client: genai.Client


def create_gemini_client(api_key: str) -> GeminiClient:
    return GeminiClient(client=genai.Client(api_key=api_key))
