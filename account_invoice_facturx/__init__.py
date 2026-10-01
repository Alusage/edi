# Odoo's PatchImportHook (odoo/_monkeypatches) sits first in sys.meta_path and
# replaces the loader of the modules it hooks. Its loader has no
# get_resource_reader, so importlib.resources.files("stdnum") raises
# FileNotFoundError: Can't open orphan path -- and every stdnum submodule that
# reads a .dat file goes down with it, factur-x included. Dropping stdnum from
# the hook set and reimporting it restores a real loader.
# Diagnostic trap: the same import works fine in `python3 -c` in this container.
import sys as _sys

try:
    from odoo._monkeypatches import HOOK_IMPORT as _HOOK_IMPORT
except ImportError:  # pragma: no cover - hook absent, nothing to undo
    _HOOK_IMPORT = None

if _HOOK_IMPORT is not None:
    _hooked = {h for h in _HOOK_IMPORT.hooks if h == "stdnum" or h.startswith("stdnum.")}
    if _hooked:
        _HOOK_IMPORT.hooks -= _hooked
        for _name in [m for m in _sys.modules if m == "stdnum" or m.startswith("stdnum.")]:
            del _sys.modules[_name]

from . import models
from .hooks import set_xml_format_in_pdf_invoice_to_facturx
