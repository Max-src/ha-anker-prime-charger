"""The device plugged into a USB-C port, as the charger identifies it.

The charger reads the USB Power Delivery identity of the device on each USB-C
port: its USB vendor and product ids, and for devices it recognises its own
brand and model numbers (status 0a00 fields bd/be, live values 0303 a8/a9).
It reports the ids fffa/fffb without a device, and 0 until it has read them.
Only port controllers of USB-PD revision 4 or later can read them: the charger
reports "usbc_identity_support" 6 then, else 2.

The library decodes these values; its cache update drops them, so the
coordinator keeps them (mqtt_extensions.EXTRA_STATE_KEYS).
"""

from __future__ import annotations

from typing import Any, Final

from .helpers import to_int
from .mqtt_extensions import IDENTITY_SUPPORT_STATE

IDENTITY_SUPPORTED: Final = 6
NO_DEVICE: Final = (0xFFFA, 0xFFFB)

# The charger's brand numbers (as the library describes them; 11 and 16 are
# brands known only by their vendor ids 339b and 2a7e)
BRANDS: Final = {
    1: "Apple",
    2: "Samsung",
    3: "Xiaomi",
    4: "Huawei",
    10: "Anker",
    12: "HP",
    13: "Dell",
    14: "Lenovo",
    15: "Microsoft",
    17: "ASUS",
    18: "MSI",
    19: "Razer",
}
# USB vendor ids of the same brands (and Google), for a device the charger
# reads but doesn't recognise
VENDORS: Final = {
    0x05AC: "Apple",
    0x04E8: "Samsung",
    0x2717: "Xiaomi",
    0x12D1: "Huawei",
    0x291A: "Anker",
    0x03F0: "HP",
    0x413C: "Dell",
    0x17EF: "Lenovo",
    0x045E: "Microsoft",
    0x0B05: "ASUS",
    0x1462: "MSI",
    0x1532: "Razer",
    0x18D1: "Google",
}


def identity_supported(data: dict[str, Any]) -> bool | None:
    """Whether the charger can read the devices' identity (None until reported)."""
    support = to_int(data.get(IDENTITY_SUPPORT_STATE))
    return None if support is None else support == IDENTITY_SUPPORTED


def connected_device(data: dict[str, Any], port_key: str) -> dict[str, Any] | None:
    """The device on a USB-C port ("usbc_1" ...), or None (no device, not read yet).

    Its name: the brand, else "VID <vendor id>"; its vendor and product ids
    (hex), and the charger's brand and model numbers (None if not recognised).
    """
    vid = to_int(data.get(f"{port_key}_device_vid"))
    pid = to_int(data.get(f"{port_key}_device_pid"))
    if (
        vid is None
        or pid is None
        or (vid, pid) == NO_DEVICE
        or not (vid or pid)
        or to_int(data.get(f"{port_key}_status")) == 0  # nothing plugged in
    ):
        return None
    brand = to_int(data.get(f"{port_key}_device_class")) or None
    model = to_int(data.get(f"{port_key}_device_code")) or None
    return {
        "name": BRANDS.get(brand or 0) or VENDORS.get(vid) or f"VID {vid:04X}",
        "vendor_id": f"{vid:04X}",
        "product_id": f"{pid:04X}",
        "brand_number": brand,
        "model_number": model,
    }
