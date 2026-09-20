"""Run idempotent metadata and telemetry migrations."""

from .settings import load_settings
from .storage import apply_migrations


def main() -> None:
    apply_migrations(load_settings())
    print("ControlSurface migrations are current")


if __name__ == "__main__":
    main()
