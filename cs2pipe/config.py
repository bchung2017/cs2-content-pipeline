import tomllib
from pathlib import Path

DEFAULT_PATH = Path("config.toml")
EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "config.example.toml"


def load(path: Path | None = None) -> dict:
    path = path or (DEFAULT_PATH if DEFAULT_PATH.exists() else EXAMPLE_PATH)
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    base = path.resolve().parent
    for key, value in cfg["paths"].items():
        p = Path(value)
        cfg["paths"][key] = p if p.is_absolute() else base / p
    return cfg
