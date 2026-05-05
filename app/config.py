from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
CHROMA_DIR = ROOT_DIR / os.getenv("CHROMA_DIR", ".chroma")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "support_docs")
VECTOR_STORE_MODE = os.getenv("VECTOR_STORE_MODE", "auto")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "resolution_agent_v1")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.70"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RUN_LOG_PATH = ROOT_DIR / "runs.jsonl"
