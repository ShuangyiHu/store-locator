from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    page: int
    page_size: int
    total: int
    items: list[T]


class CSVImportError(BaseModel):
    """One validation/import problem, scoped to a row + optional field."""

    row: int = Field(description="1-indexed row number from the CSV (header excluded)")
    field: str | None = None
    message: str


class CSVImportReport(BaseModel):
    total: int
    created: int
    updated: int
    failed: int
    errors: list[CSVImportError] = Field(default_factory=list)
    success: bool
