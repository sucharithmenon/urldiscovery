"""Base resolver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CompanyRecord, UnresolvedRecord


class BaseResolver(ABC):
    @abstractmethod
    async def resolve(self, input_url: str) -> CompanyRecord | UnresolvedRecord:
        raise NotImplementedError
