"""Compatibility import for the existing, now package-accessible authority resolver.

Historical v1 decision descriptors and manifests retain their exact contracts.
The implementation is shared with affiliation readers, not a second framework.
"""

import sys

from physics_atlas_api.storage import historical_authority as _implementation

# Preserve the original module's public/private and monkeypatch import surface.
sys.modules[__name__] = _implementation
