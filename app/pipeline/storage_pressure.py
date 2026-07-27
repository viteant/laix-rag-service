"""Disk-space guard for the public pipeline data mount."""
from dataclasses import dataclass
from shutil import disk_usage

from app.core.config import settings


@dataclass(frozen=True)
class StorageSnapshot:
    total_bytes: int
    free_bytes: int

    @property
    def free_percent(self) -> float:
        return (self.free_bytes / self.total_bytes * 100) if self.total_bytes else 0.0


class StoragePressureMonitor:
    def snapshot(self) -> StorageSnapshot:
        usage = disk_usage(settings.PIPELINE_STORAGE_PATH)
        return StorageSnapshot(total_bytes=usage.total, free_bytes=usage.free)

    def under_pressure(self) -> bool:
        return self.snapshot().free_percent <= settings.PIPELINE_MIN_FREE_SPACE_PERCENT

    def recovered(self) -> bool:
        return self.snapshot().free_percent >= settings.PIPELINE_RESUME_FREE_SPACE_PERCENT
