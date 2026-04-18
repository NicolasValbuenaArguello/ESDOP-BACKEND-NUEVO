import os
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent / ".env"

    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"La variable de entorno {name} es obligatoria")
    return value


class Config:
    DB_USER = _get_env("DB_USER", required=True)
    DB_PASSWORD = _get_env("DB_PASSWORD", required=True)
    DB_HOST = _get_env("DB_HOST", required=True)
    DB_PORT = int(_get_env("DB_PORT", default="5432"))
    DB_NAME = _get_env("DB_NAME", required=True)

    SECRET_KEY = _get_env("SECRET_KEY", required=True)
    ALGORITHM = _get_env("ALGORITHM", default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        _get_env("ACCESS_TOKEN_EXPIRE_MINUTES", default="30")
    )