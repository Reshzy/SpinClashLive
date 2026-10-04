$ErrorActionPreference = "Stop"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed. See https://docs.astral.sh/uv/"
}
uv python install 3.12
uv sync --extra dev
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}
Write-Host "Next: docker compose up -d postgres redis"
Write-Host "Then: uv run alembic upgrade head"
