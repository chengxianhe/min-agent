from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from min_agent.types import ToolResult, ToolSpec


ToolHandler = Callable[[dict[str, Any]], ToolResult]
ToolValidator = Callable[[dict[str, Any]], Optional[ToolResult]]
PermissionDescriber = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._validators: dict[str, ToolValidator] = {}
        self._permission_describers: dict[str, PermissionDescriber] = {}

    def register(
        self,
        spec: ToolSpec,
        handler: ToolHandler,
        *,
        validator: ToolValidator | None = None,
        permission_describer: PermissionDescriber | None = None,
    ) -> None:
        if spec.name in self._handlers:
            raise ValueError(f"tool already registered: {spec.name}")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler
        if validator is not None:
            self._validators[spec.name] = validator
        if permission_describer is not None:
            self._permission_describers[spec.name] = permission_describer

    def list_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def get_spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResult(success=False, error=f"unknown tool: {name}")
        try:
            return handler(args)
        except Exception as exc:
            return ToolResult(success=False, error=f"tool {name} failed: {exc}")

    def validate_call(self, name: str, args: dict[str, Any]) -> ToolResult | None:
        validator = self._validators.get(name)
        return validator(args) if validator is not None else None

    def permission_details(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        describer = self._permission_describers.get(name)
        return describer(args) if describer is not None else {}
