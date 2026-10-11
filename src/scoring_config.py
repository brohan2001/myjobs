"""Myjobs-specific scoring constants and keyword loaders.

Separated from src/config.py (which is now the pydantic-settings Settings class)
so the two don't conflict.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
# Personal files live in private/ (gitignored). Phase 1 replaces this with profile lookups.
PRIVATE_DIR = Path(os.getenv("MYJOBS_PRIVATE_DIR", BASE_DIR / "private"))
RESUME_DIR = Path(os.getenv("RESUME_DIR", PRIVATE_DIR / "resumes"))
PROFILE_PATH = Path(os.getenv("PROFILE_PATH", PRIVATE_DIR / "profile.txt"))

SKILL_GROUPS: dict[str, tuple[float, list[str]]] = {
    "languages": (1.0, [
        "python", "java", "javascript", "typescript", "golang", "go",
        "c++", "swift", "scala", "ruby", "rust", "bash", "shell", "kotlin",
    ]),
    "frameworks": (1.2, [
        "react", "node.js", "nodejs", "django", "flask", "express",
        "next.js", "nextjs", "fastapi", "spring", "rails", "flutter",
        "graphql", "rest api", "grpc", "vue", "angular",
    ]),
    "cloud": (1.1, [
        "aws", "gcp", "azure", "lambda", "ecs", "eks", "sqs", "sns",
        "kubernetes", "k8s", "docker", "terraform", "ansible",
        "ci/cd", "jenkins", "github actions", "cloudformation",
    ]),
    "ml": (1.3, [
        "pytorch", "tensorflow", "scikit-learn", "hugging face", "transformers",
        "llm", "nlp", "opencv", "pandas", "numpy", "spark", "mlflow",
        "wandb", "langchain", "rag", "fine-tuning",
    ]),
    "databases": (0.9, [
        "postgresql", "postgres", "mongodb", "mysql", "redis", "firebase",
        "elasticsearch", "cassandra", "dynamodb", "sqlite", "bigquery",
    ]),
    "tools": (0.8, [
        "git", "kafka", "airflow", "grafana", "prometheus",
        "linux", "unix", "jira", "agile", "scrum", "datadog",
    ]),
}

ROLE_PRIORITY: dict[str, float] = {
    "backend":   1.00,
    "cloud":     0.90,
    "fullstack": 0.85,
    "frontend":  0.75,
    "mobile":    0.70,
    "network":   0.65,
    "ds":        0.55,
    "ml":        0.50,
    "other":     0.20,
}

SCORE_WEIGHTS = {
    "skill":   35,
    "role":    25,
    "visa":    20,
    "recency": 10,
    "company": 10,
}

TIER_SCORES = {1: 1.0, 2: 0.65, 3: 0.35}
INDUSTRY_BONUS = {"fintech": 0.10, "tech": 0.05, "enterprise": 0.0}

RECENCY_BREAKPOINTS = [
    (0,  1.00),
    (1,  0.90),
    (3,  0.80),
    (7,  0.60),
    (14, 0.35),
    (30, 0.15),
]

RESUME_MAP = {
    "backend":   RESUME_DIR / os.getenv("RESUME_SWE",     "resume_swe.pdf"),
    "frontend":  RESUME_DIR / os.getenv("RESUME_SWE",     "resume_swe.pdf"),
    "fullstack": RESUME_DIR / os.getenv("RESUME_SWE",     "resume_swe.pdf"),
    "mobile":    RESUME_DIR / os.getenv("RESUME_SWE",     "resume_swe.pdf"),
    "cloud":     RESUME_DIR / os.getenv("RESUME_CLOUD",   "resume_cloud.pdf"),
    "network":   RESUME_DIR / os.getenv("RESUME_NETWORK", "resume_network.pdf"),
    "ds":        RESUME_DIR / os.getenv("RESUME_DS",      "resume_ds.pdf"),
    "ml":        RESUME_DIR / os.getenv("RESUME_ML",      "resume_ml.pdf"),
    "other":     RESUME_DIR / os.getenv("RESUME_SWE",     "resume_swe.pdf"),
}

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")


def load_visa_keywords() -> dict[str, list[str]]:
    with open(DATA_DIR / "visa_keywords.json") as f:
        return json.load(f)


def load_role_keywords() -> dict[str, list[str]]:
    with open(DATA_DIR / "role_keywords.json") as f:
        return json.load(f)


def load_h1b_sponsors() -> dict:
    h1b_path = DATA_DIR / "h1b_sponsors.json"
    if not h1b_path.exists():
        return {}
    with open(h1b_path) as f:
        return json.load(f)
