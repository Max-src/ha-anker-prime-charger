"""Entities opt in to in-place entity id changes (Home Assistant 2026.11+).

From 2026.11, renaming an entity's id updates it in place instead of removing
and adding it again. Until 2027.11 a custom integration's entity keeps the old
behaviour if one of its own classes defines an add/remove lifecycle method
without also defining async_entity_id_changed. Each such class must opt in, so
classes added later are covered too.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import custom_components.anker_prime_charger as package
from homeassistant.helpers.entity import Entity

LIFECYCLE = (
    "async_prepare_to_add_to_hass",
    "async_added_to_hass",
    "async_will_remove_from_hass",
)


def _own_entity_classes() -> list[type]:
    classes = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.name == "solixapi":
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for cls in vars(module).values():
            if (
                inspect.isclass(cls)
                and issubclass(cls, Entity)
                and cls.__module__.startswith(package.__name__)
            ):
                classes[cls.__qualname__] = cls
    return list(classes.values())


def test_entities_opt_in_to_in_place_entity_id_changes() -> None:
    """Every own class with an add/remove method also defines the rename hook."""
    classes = _own_entity_classes()
    assert len(classes) > 20  # the scan found the platforms' classes
    missing = [
        cls.__qualname__
        for cls in classes
        if any(name in vars(cls) for name in LIFECYCLE)
        and "async_entity_id_changed" not in vars(cls)
    ]
    assert missing == []
