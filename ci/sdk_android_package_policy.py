"""Android entry point for the shared Maven package caller policy."""

from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from . import sdk_core_package_policy as shared
else:
    import sdk_core_package_policy as shared


def prepare(*args, **kwargs):
    return shared.prepare(*args, component="sdk-android", **kwargs)


def main(argv=None):
    return shared.main(argv, component="sdk-android")


if __name__ == "__main__":
    raise SystemExit(main())
