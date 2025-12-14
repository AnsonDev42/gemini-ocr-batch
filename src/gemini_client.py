from __future__ import annotations

import os
from dataclasses import dataclass

from braintrust.wrappers.google_genai import setup_genai
from google import genai


@dataclass(frozen=True)
class GeminiClient:
    client: genai.Client


def create_gemini_client(api_key: str) -> GeminiClient:
    setup_genai(
        project_name=os.getenv("BRAINTRUST_PROJECT_NAME"),
        api_key=os.environ.get("BRAINTRUST_API_KEY"),
    )
    return GeminiClient(client=genai.Client(api_key=api_key))
