import logging


def configure_logging() -> None:
    """Configure CLI diagnostics on stderr without replacing existing handlers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
