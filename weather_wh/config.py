"""Settings from environment variables (a local .env file is read if present).

Everything is optional: with no keys the pipeline still collects Open-Meteo
forecasts into the local data folder.
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env reader (KEY=value lines) so we don't need another dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    aemet_api_key: str | None
    hf_bucket: str | None
    hf_token: str | None

    @property
    def publishes(self) -> bool:
        return bool(self.hf_bucket and self.hf_token)


def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR") or "data"),
        aemet_api_key=os.getenv("AEMET_API_KEY") or None,
        hf_bucket=os.getenv("HF_BUCKET") or None,
        hf_token=os.getenv("HF_TOKEN") or None,
    )
