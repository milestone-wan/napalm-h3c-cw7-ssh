"""Device profile primitives for H3C Comware platforms."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import FrozenSet, Optional

from .exceptions import UnsupportedProfileError


class DeviceRole(str, Enum):
    """Supported H3C Comware device roles."""

    SWITCH = "switch"
    ROUTER = "router"
    UNKNOWN = "unknown"


class ComwareMajorVersion(IntEnum):
    """Supported Comware major versions."""

    V7 = 7
    V9 = 9


SUPPORTED_BRAND = "h3c"
SUPPORTED_MAJOR_VERSIONS = frozenset({ComwareMajorVersion.V7, ComwareMajorVersion.V9})
SUPPORTED_ROLES = frozenset({DeviceRole.SWITCH, DeviceRole.ROUTER})
FIREWALL_MARKERS = frozenset({"secpath", "firewall", "fw", "f100", "f500", "f1000", "f5000"})
SWITCH_MARKERS = frozenset({"ls", "ce", "switch"})
ROUTER_MARKERS = frozenset({"msr", "cr", "sr", "router"})


@dataclass(frozen=True)
class DeviceProfile:
    """Normalized platform identity used by command and parser selection."""

    brand: str = SUPPORTED_BRAND
    major_version: Optional[ComwareMajorVersion] = None
    role: DeviceRole = DeviceRole.UNKNOWN
    model: str = ""
    os_version: str = ""
    capabilities: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def is_supported(self) -> bool:
        return (
            self.brand.lower() == SUPPORTED_BRAND
            and self.major_version in SUPPORTED_MAJOR_VERSIONS
            and self.role in SUPPORTED_ROLES
        )

    def require_supported(self) -> None:
        if not self.is_supported:
            raise UnsupportedProfileError(
                "Unsupported H3C Comware profile: "
                f"brand={self.brand!r}, version={self.major_version!r}, "
                f"role={self.role.value!r}, model={self.model!r}"
            )

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


def detect_comware_major_version(text: str) -> Optional[ComwareMajorVersion]:
    """Detect the Comware major version from version text."""
    if not text:
        return None

    normalized = text.lower()
    if re.search(r"comware\s+software.*version\s+9|version\s+9\.", normalized):
        return ComwareMajorVersion.V9
    if re.search(r"comware\s+software.*version\s+7|version\s+7\.", normalized):
        return ComwareMajorVersion.V7
    return None


def classify_device_role(model: str, text: str = "") -> DeviceRole:
    """Classify supported switch/router roles from model or version text."""
    normalized_model = model.strip().lower()
    normalized_text = text.strip().lower()
    combined = f"{normalized_model} {normalized_text}"

    if _contains_marker(combined, FIREWALL_MARKERS):
        raise UnsupportedProfileError("H3C firewall platforms are outside this driver's target scope")
    if _contains_marker(combined, ROUTER_MARKERS):
        return DeviceRole.ROUTER
    if _contains_marker(combined, SWITCH_MARKERS) or re.match(r"^s\d+", normalized_model):
        return DeviceRole.SWITCH
    return DeviceRole.UNKNOWN


def build_device_profile(
    model: str = "",
    os_version: str = "",
    version_output: str = "",
    capabilities: Optional[FrozenSet[str]] = None,
) -> DeviceProfile:
    """Build a profile from discovered facts and raw version output."""
    major_version = detect_comware_major_version("\n".join((os_version, version_output)))
    role = classify_device_role(model, version_output)
    return DeviceProfile(
        major_version=major_version,
        role=role,
        model=model,
        os_version=os_version,
        capabilities=capabilities or frozenset(),
    )


def _contains_marker(text: str, markers: FrozenSet[str]) -> bool:
    for marker in markers:
        if re.search(rf"(^|[^a-z0-9]){re.escape(marker)}([^a-z0-9]|$)", text):
            return True
    return False
