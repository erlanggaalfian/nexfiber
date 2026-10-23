"""Failure-string detection (PRD 4.3): OLT CLI has no exit code, so success must be proven
from output content, never assumed from "no exception".
"""

# ZTE ZXA10 CLI error fragments (case-insensitive substring match). Confirmed against
# the running-config transcripts provided for this project; extended with the vendor's
# publicly documented CLI error wording where no real transcript was available.
ZTE_ERROR_PATTERNS = [
    "invalid input",
    "unknown command",
    "incomplete command",
    "ambiguous command",
    "operation failed",
    "% there is no",
    "command rejected",
    "already exist",
]

def is_error_output(output: str, patterns: list[str]) -> bool:
    lowered = output.lower()
    return any(p in lowered for p in patterns)
