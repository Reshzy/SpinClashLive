# Color Rush Live — operator console

Native PySide6 console. It talks only to the authenticated backend API. It has no SQL, Redis, or scoring engine.

## Launch (Windows PowerShell)

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv sync --extra desktop --extra dev
$env:COLOR_RUSH_API_BASE = "http://127.0.0.1:8000"
uv run python -m color_rush_desktop
```

Bootstrap owner (backend): `owner` / `change-me-owner` after `uv run python -m color_rush.bootstrap`.

Closing the console does not stop the API or worker.

## Packaging

```powershell
uv run pyinstaller desktop/packaging/color_rush_desktop.spec
```

Output: `dist/ColorRushLive/`. Exclude secrets from the bundle (see `packaging/LICENSES.md`).
