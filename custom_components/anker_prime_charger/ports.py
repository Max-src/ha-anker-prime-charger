"""The charger's output ports, and the Home Assistant device of each.

The charger has four USB-C ports and two USB-A ports. The two USB-A ports have
their own readings (power, voltage, current, connected) and labels, but share
everything else (on/off, timer, schedule, custom power limit): the charger
has a single control for both. So Home Assistant has five port devices:
USB-C 1-4 and "USB-A" (both ports), child devices of the charger's device.

The same port has different names in different places:
- MQTT controls, timers and schedules: "usbc_1" ... "usba"
- MQTT readings: "usbc_1" ... "usba_1", "usba_2"
- custom charging mode: "c1" ... "a"
- custom profiles in the Anker cloud: "C1" ... "C4", "A"
- port labels in the Anker cloud: "C1" ... "A1", "A2"

Everything else that is specific to a port (maximum power, priority) is here
too; the other modules derive their tables from PORTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Final

from homeassistant.helpers.device_registry import ChildDeviceInfo

from .const import DOMAIN


@dataclass(frozen=True)
class Port:
    """One port device (USB-A: both USB-A ports)."""

    key: str  # MQTT controls, timers, schedules
    label: str  # shown in Home Assistant
    custom: str  # custom charging mode
    outputs: tuple[str, ...]  # MQTT readings, one per physical port
    remarks: tuple[str, ...]  # port label names in the Anker cloud
    profile: str  # port name in the custom profiles of the Anker cloud
    max_power: int  # W, custom mode limit (USB-A: both ports together)
    output_max_power: float  # W, of each physical port (Anker's user guide)

    @property
    def is_usb_c(self) -> bool:
        """Whether this is a USB-C port."""
        return self.custom != "a"

    def output_prefix(self, output: str) -> str:
        """Translation key prefix of one physical port's entities on this device.

        USB-A has two physical ports on one device: "a1_", "a2_". USB-C: none.
        """
        return "" if self.is_usb_c else f"a{output[-1]}_"


PORTS: Final = (
    Port("usbc_1", "USB-C 1", "c1", ("usbc_1",), ("C1",), "C1", 140, 140),
    Port("usbc_2", "USB-C 2", "c2", ("usbc_2",), ("C2",), "C2", 100, 100),
    Port("usbc_3", "USB-C 3", "c3", ("usbc_3",), ("C3",), "C3", 100, 100),
    Port("usbc_4", "USB-C 4", "c4", ("usbc_4",), ("C4",), "C4", 100, 100),
    Port("usba", "USB-A", "a", ("usba_1", "usba_2"), ("A1", "A2"), "A", 24, 22.5),
)
USB_C_PORTS: Final = tuple(port for port in PORTS if port.is_usb_c)
USB_A_PORT: Final = next(port for port in PORTS if not port.is_usb_c)

# Priority ports (Connection priority mode): up to two USB-C ports. The command
# takes a bitmask (bit 0 = USB-C 1 ...); the status reports a flag per port
# (<key>_priority): 1 normal, 2 priority. Options: "off", "c1", ..., "c1_c2", ...
PRIORITY_NORMAL: Final = 1
PRIORITY_ON: Final = 2
PRIORITY_OPTIONS: Final[dict[str, int]] = {
    "off": 0,
    **{port.custom: 1 << idx for idx, port in enumerate(USB_C_PORTS)},
    **{
        f"{a.custom}_{b.custom}": (1 << ia) | (1 << ib)
        for (ia, a), (ib, b) in combinations(enumerate(USB_C_PORTS), 2)
    },
}


def port_device_info(
    charger_sn: str, charger_name: str, charger_device_id: str, port: Port
) -> ChildDeviceInfo:
    """The port's device: a child device of the charger's device.

    A child device (Home Assistant 2026.9) is a logical part of its parent
    device. A port device created by an earlier version as a separate device
    is converted to a child device by Home Assistant, keeping its id.
    """
    return ChildDeviceInfo(
        identifiers={(DOMAIN, f"{charger_sn}_{port.key}")},
        name=f"{charger_name} {port.label}",
        parent_device_id=charger_device_id,
    )
