"""Backward-compatible CLI/import for the packaged decision archive helper.

The archive contract and implementation live in the importable storage package.
Alias the module itself when imported: legacy private helpers, constants and
test monkeypatches continue to address that single implementation namespace.
"""

import sys

from physics_atlas_api.storage import historical_decision_archive as _implementation

if __name__ == "__main__":
    sys.exit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
