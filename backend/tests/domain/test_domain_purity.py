from pathlib import Path

FORBIDDEN = ("fastapi", "PySide6", "PyQt", "sqlalchemy", "redis", "googleapiclient", "youtube")


def test_domain_modules_have_no_framework_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "color_rush" / "domain"
    for path in root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped.startswith(("import ", "from ")):
                for token in FORBIDDEN:
                    assert token not in stripped, f"{path} imports {token}"
