from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in requirements
    load_dotenv = None


def load_project_env(root_dir):
    if not load_dotenv:
        return

    root = Path(root_dir)
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.domain", override=True)
