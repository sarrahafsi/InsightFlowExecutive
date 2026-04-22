from typing import Type, Any
from .base import BaseConnector
from .schemas import SourceType


class ConnectorRegistry:
    """
    Central registry that maps SourceType → connector class.
    Use the @ConnectorRegistry.register decorator on each connector.

    Example:
        @ConnectorRegistry.register(SourceType.SLACK)
        class SlackConnector(BaseConnector): ...

        connector = ConnectorRegistry.build(SourceType.SLACK, config={...})
    """

    _registry: dict[SourceType, Type[BaseConnector]] = {}

    @classmethod
    def register(cls, source: SourceType):
        """Decorator — registers a connector class for a given source."""
        def decorator(connector_cls: Type[BaseConnector]):
            connector_cls.source = source
            cls._registry[source] = connector_cls
            return connector_cls
        return decorator

    @classmethod
    def build(cls, source: SourceType, config: dict[str, Any]) -> BaseConnector:
        """Instantiate a registered connector with its config."""
        if source not in cls._registry:
            raise ValueError(
                f"No connector registered for source '{source}'. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[source](config)

    @classmethod
    def available_sources(cls) -> list[SourceType]:
        return list(cls._registry.keys())
