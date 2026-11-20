"""Fail closed before executing imported tooling in a signing process."""

from collections.abc import Mapping
import os


SIGNING_SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


def require_no_signing_secret(environment: Mapping[str, str]) -> None:
    """Reject even an empty signing variable in either supplied or live state."""
    if SIGNING_SECRET in environment or SIGNING_SECRET in os.environ:
        raise ValueError("Imported tooling must run outside the product signing-secret context")
