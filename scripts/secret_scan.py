"""Fail if tracked files look like they contain live secrets."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "node_modules", "dist", "__pycache__", ".mypy_cache"}
PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"GOCSPX-[0-9A-Za-z_-]+"),
    re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
)
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ts",
    ".env",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".txt",
    ".ps1",
    ".sh",
    ".spec",
}
ALLOW = {ROOT / ".env.example"}
LIVE_KEY = re.compile(r"GOOGLE_API_KEY=AIza[0-9A-Za-z_-]{20,}")


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if path.resolve() in {item.resolve() for item in ALLOW}:
            if LIVE_KEY.search(text):
                hits.append(str(path.relative_to(ROOT)))
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                hits.append(str(path.relative_to(ROOT)))
                break
    if hits:
        print("possible secrets:")
        for item in hits:
            print(f"  {item}")
        return 1
    print("secret scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
