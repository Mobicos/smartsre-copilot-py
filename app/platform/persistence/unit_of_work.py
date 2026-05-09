"""Unit of Work helpers for application-level transaction boundaries."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlmodel import Session

from app.platform.persistence.database import get_engine


class UnitOfWork:
    """Own one SQLModel session and commit or roll back as a single unit."""

    def __init__(self) -> None:
        self.session = Session(bind=get_engine())
        self._committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.session.rollback()
        elif not self._committed:
            self.session.commit()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()
        self._committed = True
