"""Hold independently pinned SDK phase selections before observing a campaign.

The protected caller supplies policy files and their independently approved
digests. This is input custody, not original-upload or release admission.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
from types import MappingProxyType

from ci.sdk_apple_js_campaign_election import load_family_election as load_apple_js
from ci.sdk_campaign_core_android_election import load_core_android_election
from ci.sdk_campaign_native_policy import load_native_election
from products.inventory import read_regular_file_bytes, require_sha256, sha256_bytes
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


_LOADERS = {
    "core-android": load_core_android_election,
    "native": load_native_election,
    "apple-js": load_apple_js,
}


@contextmanager
def held_pinned_sdk_campaign_election(policy_files: Mapping[str, Path],
        expected_sha256: Mapping[str, str]):
    """Yield exact 61 caller selections, rechecking every pinned file on exit.

    Enter this context before any state/catalog observation. The digest source
    must be protected independently of these files; matching self-supplied
    digests do not grant trust.
    """
    require_no_signing_secret(os.environ)
    if (not isinstance(policy_files, Mapping) or not isinstance(expected_sha256, Mapping)
            or set(policy_files) != set(_LOADERS) or set(expected_sha256) != set(_LOADERS)):
        raise ValueError("SDK campaign election requires all three independent families")
    fresh, reused, pinned, seen_paths = {}, {}, {}, set()
    for family, loader in _LOADERS.items():
        path = policy_files[family]
        if (not isinstance(path, Path) or not path.is_absolute()
                or path.resolve(strict=True) != path):
            raise ValueError("SDK election policy requires an absolute normalized caller-owned file")
        if path in seen_paths:
            raise ValueError("SDK election policy files must be distinct")
        seen_paths.add(path)
        expected = require_sha256(expected_sha256[family], f"{family} SDK election digest")
        family_fresh, family_reused, raw = loader(path)
        if sha256_bytes(raw) != expected:
            raise ValueError(f"{family} SDK election differs from its independent digest")
        if set(fresh) & (set(family_fresh) | set(family_reused)) or \
                set(reused) & (set(family_fresh) | set(family_reused)):
            raise ValueError("SDK election repeats a phase across families")
        fresh.update(family_fresh)
        reused.update(family_reused)
        pinned[family] = (path, raw)
    if set(fresh) & set(reused) or set(fresh) | set(reused) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK election does not cover exactly 61 disjoint phases")
    if len({request["expected_product_version"] for request in (*fresh.values(), *reused.values())}) != 1:
        raise ValueError("SDK election requires one exact SDK version")
    selections_before = deepcopy((fresh, reused))
    try:
        yield MappingProxyType(fresh), MappingProxyType(reused)
    finally:
        require_no_signing_secret(os.environ)
        if (fresh, reused) != selections_before or any(
                read_regular_file_bytes(path, max_bytes=1024 * 1024,
                    reject_symlink_parents=True) != raw for path, raw in pinned.values()):
            raise ValueError("SDK election changed during campaign observation")
