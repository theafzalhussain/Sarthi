"""Standard contract for external services."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ConnectorResult:
    ok: bool; message: str=""; data: dict[str,Any]=field(default_factory=dict)
    @classmethod
    def success(cls,message="",**data): return cls(True,message,data)
    @classmethod
    def failure(cls,message): return cls(False,message,{})

class Connector(ABC):
    name="connector"
    @abstractmethod
    async def available(self)->bool: raise NotImplementedError
    @abstractmethod
    async def health(self)->ConnectorResult: raise NotImplementedError
