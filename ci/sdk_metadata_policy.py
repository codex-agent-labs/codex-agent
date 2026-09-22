"""Explicit invocation policy for concrete metadata replay, never carrier trust.

Policy descriptors are caller-owned canonical JSON, not product artifacts. Their
exact fields are evidenceRoot, records and policy; the existing concrete adapter
validates records/policy. Current repository/revision come from the invocation's
verified plan. This loader neither authenticates hosted tooling nor skips replay.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys
from products.signing_isolation import require_no_signing_secret


_OPTIONS = ("sdk_facade_metadata_policy", "sdk_android_metadata_policy")


def add_metadata_admission_arguments(parser):
    for name in _OPTIONS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path,
                            help="Independent caller-owned metadata replay policy; never retained evidence")


def _read(path):
    return read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)


@contextmanager
def metadata_admission_options(args):
    """Hold descriptors across execution; consume only policy flags from dicts.

Namespaces remain unchanged. With no flags this is a no-I/O empty context, so
legacy CLI invocations keep their existing behavior and rejection boundaries.
"""
    values = vars(args) if not isinstance(args, dict) else args
    paths = {name: values.get(name) for name in _OPTIONS if values.get(name) is not None}
    if isinstance(args, dict):
        for name in _OPTIONS:
            args.pop(name, None)
    if not paths:
        yield {}
        return

    import product_reuse
    from products.sdk_facade_metadata_admission import FacadeMetadataAdmission
    from products.sdk_android_metadata_admission import AndroidMetadataAdmission

    require_no_signing_secret(os.environ)
    root = Path(values.get("repository_root") or Path(__file__).resolve().parents[1]).resolve(strict=True)
    plan_path = values.get("plan")
    if plan_path is None and values.get("input_root") is not None:
        plan_path = Path(values["input_root"]) / "product-resume-inputs/plan/impact-plan.json"
    if plan_path is None:
        raise ValueError("Metadata caller policy requires the current invocation plan")
    plan_path = Path(plan_path).absolute()
    plan_bytes = _read(plan_path)
    plan = product_reuse._validate_plan(plan_path, root)
    paths = {name: Path(path).absolute() for name, path in paths.items()}
    if any(path.resolve(strict=True) != path for path in paths.values()):
        raise ValueError("Metadata caller policy paths must be normalized and non-symbolic")
    originals = {name: _read(path) for name, path in paths.items()}

    def unchanged():
        require_no_signing_secret(os.environ)
        if (_read(plan_path) != plan_bytes
                or any(_read(paths[name]) != raw for name, raw in originals.items())):
            raise ValueError("Metadata caller plan or policy changed during execution")

    try:
        descriptors = {name: require_exact_keys(load_canonical_json_bytes(raw),
            {"evidenceRoot", "records", "policy"}, "Caller metadata policy descriptor")
            for name, raw in originals.items()}
        for descriptor in descriptors.values():
            evidence = descriptor["evidenceRoot"]
            if not isinstance(evidence, str) or not Path(evidence).is_absolute():
                raise ValueError("Metadata evidence root must be an absolute path")
            evidence = Path(evidence)
            if evidence.resolve(strict=True) != evidence:
                raise ValueError("Metadata evidence root must be normalized and non-symbolic")
            if any(path == evidence or evidence in path.parents for path in paths.values()):
                raise ValueError("Metadata caller policy must be outside retained evidence")
        classes = dict(zip(_OPTIONS, (FacadeMetadataAdmission, AndroidMetadataAdmission)))
        options = {name.replace("_policy", "_admission"): classes[name](
            descriptor["evidenceRoot"], descriptor["records"], repository=root,
            policy_revision=plan["validationCommit"], policy=descriptor["policy"])
            for name, descriptor in descriptors.items()}
        unchanged()
        yield options
    finally:
        unchanged()
