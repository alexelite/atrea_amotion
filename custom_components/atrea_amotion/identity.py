"""Stable hardware identity shared by all entity platforms."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def serial_number(data) -> str | None:
    """Return the production number shown as SN in discovery."""
    value = data.get("production_number")
    return str(value).strip() if value is not None and str(value).strip() else None


def device_identity(entry) -> str:
    """Keep a persisted identity independent of the name and network address."""
    if identity := entry.data.get("device_identity"):
        return identity
    if serial := serial_number(entry.data):
        return f"production:{serial}"
    if board := entry.data.get("board_number"):
        return f"board:{str(board).strip().lower()}"
    return f"entry:{entry.entry_id}"


def device_info(entry, coordinator, name) -> DeviceInfo:
    """Expose the hardware serial alongside the stable device identifier."""
    return DeviceInfo(
        identifiers={(DOMAIN, device_identity(entry))},
        manufacturer="Atrea CZ",
        model=coordinator.model,
        name=name,
        sw_version=coordinator.version,
        serial_number=serial_number(entry.data),
    )


class AtreaAvailability:
    """Expose connection availability consistently on every platform."""

    @property
    def available(self) -> bool:
        return getattr(self.coordinator, "available", True)
