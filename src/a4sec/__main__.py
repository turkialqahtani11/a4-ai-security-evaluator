"""Allow ``python -m a4sec``."""

from a4sec.cli import app


def main() -> None:
    """Entry point for ``python -m a4sec`` and the ``a4sec`` console script."""
    app(prog_name="a4sec")


if __name__ == "__main__":
    main()
