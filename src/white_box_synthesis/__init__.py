"""White-box synthesis with source-wording provenance."""

from .records import OPERATION_POLICY_VERSION, SCHEMA_VERSION
from .synthesis import POLICY_VERSION as SYNTHESIS_POLICY_VERSION
from .synthesis import SCHEMA_VERSION as SYNTHESIS_SCHEMA_VERSION
from .synthesis import synthesise
from .verify import verify

__all__ = [
    "OPERATION_POLICY_VERSION",
    "SCHEMA_VERSION",
    "SYNTHESIS_POLICY_VERSION",
    "SYNTHESIS_SCHEMA_VERSION",
    "synthesise",
    "verify",
]
__version__ = "0.2.0"
