from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class DiscoveredAsset:
    """Stable public metadata obtained before a file is downloaded."""

    logical_identity: str
    canonical_filename: str
    source_url: str | None
    metadata: dict[str, str] = field(default_factory=dict)


class PublicSourceConnector(Protocol):
    """A connector only discovers assets; downloads are handled in a later phase."""

    def discover(self) -> list[DiscoveredAsset]: ...
