"""Stage an externally approved SDK campaign authority for official upload.

The caller must custody the source file and its digest independently. This
command validates and packages those bytes; it does not approve or sign them.
"""

import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    require_sha256, sha256_bytes,
)
from products.signing_isolation import require_no_signing_secret


_NAME = "sdk-campaign-authority.json"


def stage_sdk_campaign_authority(source: Path, approved_sha256: str,
        destination: Path) -> dict:
    """Publish one unchanged authority file; return external input provenance."""
    require_no_signing_secret(os.environ)
    approved = require_sha256(approved_sha256, "approved SDK authority digest")
    source = Path(source)
    with held_pinned_sdk_campaign_authority(source, approved):
        raw = read_regular_file_bytes(source, max_bytes=1024 * 1024,
            reject_symlink_parents=True)
    with TemporaryDirectory(prefix="sdk-authority-stage-", dir=source.parent) as temporary:
        staged = Path(temporary) / "upload"
        staged.mkdir()
        (staged / _NAME).write_bytes(raw)
        publish_regular_tree(staged, destination, expected_inventory=[{
            "relativePath": _NAME, "bytes": len(raw), "sha256": approved,
        }])
    require_no_signing_secret(os.environ)
    return {"inputPath": str(source), "inputSha256": approved,
            "outputPath": str(Path(destination) / _NAME),
            "outputSha256": sha256_bytes(raw)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--approved-authority", type=Path, required=True)
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = stage_sdk_campaign_authority(args.approved_authority,
            args.approved_sha256, args.destination)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(canonical_json_bytes(result).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
