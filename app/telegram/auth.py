"""Alias: ``python -m app.telegram.auth`` → infrastructure auth."""

from app.infrastructure.telegram.auth import authorize, main

__all__ = ["authorize", "main"]

if __name__ == "__main__":
    main()
