"""共用响应模型：分页、列表包装。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=200)


class PagedResult(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    items: list[T]
