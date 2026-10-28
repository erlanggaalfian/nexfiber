"""Failure-string detection (PRD 4.3): OLT CLI has no exit code, so success must be proven
from output content, never assumed from "no exception".
"""

# ZTE ZXA10 CLI error fragments (case-insensitive substring match). Confirmed against
# the running-config transcripts provided for this project; extended with the vendor's
# publicly documented CLI error wording where no real transcript was available.
# "%error" / "%code" are the generic forms of the outputs actually seen in this repo:
# "%Error 20202: Invalid input detected" (fixture zte_show_interface_port_status.txt),
# "%Error 20203: Incomplete command" (zte_c320 docstring), "%Error 20206: Unrecognized
# command" and "%Code 63953-GPONRM : Flow does not exist." (zte_onu_actions docstrings),
# "%Code 62310-GPONSRV : No related information to show" (list_unconfigured parser).
# They catch error codes not listed individually below, without inventing new wording.
ZTE_ERROR_PATTERNS = [
    "invalid input",
    "unknown command",
    "incomplete command",
    "ambiguous command",
    "operation failed",
    "% there is no",
    "command rejected",
    "already exist",
    "%error",
    "%code",
]

# Confirmation prompts ZTE CLI issues for destructive commands (e.g. "no onu <id>").
# These are NOT auto-answered: send_command_timing only waits, it never sends "y"
# (the old ssh.py comment claiming otherwise was wrong). A command whose output ends
# on one of these prompts is treated as pending-confirmation, answered "n" to abort,
# and reported as a failure — never as a silent success.
CONFIRMATION_PROMPTS = ["(y/n)", "[y/n]", "continue?"]


def is_error_output(output: str, patterns: list[str]) -> bool:
    lowered = output.lower()
    return any(p in lowered for p in patterns)


def has_confirmation_prompt(output: str) -> bool:
    lowered = output.lower()
    return any(p in lowered for p in CONFIRMATION_PROMPTS)
