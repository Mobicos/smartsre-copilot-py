"""FastAPI dependency-injection helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.platform.persistence.database import get_db

SessionDep = Annotated[Session, Depends(get_db)]
