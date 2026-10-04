"""Capsule CLI package — atomic knowledge for agents."""
import sys
from pathlib import Path

# Defend against conflicting editable finders (e.g. other repos mapping generic 'services')
_capsule_root = Path(__file__).resolve().parent.parent
_capsule_services = str(_capsule_root / "services")

for _f in list(sys.meta_path):
    _mod_name = getattr(_f, "__module__", "")
    if "editable" in _mod_name and "kapsule" not in _mod_name:
        _mod = sys.modules.get(_mod_name)
        if _mod and hasattr(_mod, "MAPPING"):
            if "services" in _mod.MAPPING and _mod.MAPPING["services"] != _capsule_services:
                del _mod.MAPPING["services"]

if str(_capsule_root) not in sys.path:
    sys.path.insert(0, str(_capsule_root))
