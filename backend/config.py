"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members — 6 models split across two teams.
# Order matters: strategists first, then builders. The UI renders tabs in this
# order, so keeping each tier contiguous makes the visual grouping cleaner.
COUNCIL_MODELS = [
    # Strategists — high-level reviewers (the original 3)
    "anthropic/claude-opus-4.7",
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.4",
    # Builders — implementation realists (think like coding agents)
    "openai/gpt-5.3-codex",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-3-flash-preview",
]

# Each council member belongs to exactly one tier. Cross-review uses this: a
# strategist reviewer is shown only builder responses to rank, and vice versa.
MODEL_TIERS = {
    "anthropic/claude-opus-4.7": "strategist",
    "google/gemini-3.1-pro-preview": "strategist",
    "openai/gpt-5.4": "strategist",
    "openai/gpt-5.3-codex": "builder",
    "anthropic/claude-sonnet-4.6": "builder",
    "google/gemini-3-flash-preview": "builder",
}

STRATEGIST_MODELS = [m for m, t in MODEL_TIERS.items() if t == "strategist"]
BUILDER_MODELS = [m for m, t in MODEL_TIERS.items() if t == "builder"]


def tier_for(model_id: str) -> str:
    """Return the tier for a council model id. Defaults to 'strategist' for
    unknown ids so a typo can't accidentally exile a model into an empty tier."""
    return MODEL_TIERS.get(model_id, "strategist")


# Chairman model — synthesizes final response from all 6 perspectives.
CHAIRMAN_MODEL = "anthropic/claude-opus-4.7"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
