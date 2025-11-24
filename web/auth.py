"""Lightweight role helper for TagTracker web CGIs.

Responsibilities (kept minimal on purpose):
    - Read and validate the role from the environment (set by Apache as TT_ROLE).
    - Provide a simple ordering-aware check (attendant < user < admin).
    - Map WHAT_* codes to their minimum required role.

"""

from __future__ import annotations

import os
from typing import Mapping, Optional

import web.web_common as cc

# Role constants and ordering (supersets: attendant < user < admin)
ROLE_ATTENDANT = "attendant"
ROLE_USER = "user"
ROLE_ADMIN = "admin"

ROLE_ORDER = [ROLE_ATTENDANT, ROLE_USER, ROLE_ADMIN]
VALID_ROLES = frozenset(ROLE_ORDER)

# Environment variable Apache should set to convey the role.
ENV_ROLE = "TT_ROLE"


def get_current_role(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Return the current role string from the environment, or None if not set."""
    env = env or os.environ
    return env.get(ENV_ROLE)


def is_valid_role(role: str) -> bool:
    """Return True if role is one of the known roles."""
    return role in VALID_ROLES


def role_rank(role: str) -> int:
    """Return the integer rank for the role (higher means more privilege)."""
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return -1


def role_at_least(role: str, required: str) -> bool:
    """Return True if ``role`` is >= ``required`` in privilege order."""
    return role_rank(role) >= role_rank(required) >= 0


# Map WHAT_* codes to the minimum role required.
WHAT_MIN_ROLE: dict[str, str] = {
    # Items for attendants
    cc.WHAT_AUDIT: ROLE_ATTENDANT,
    cc.WHAT_ESTIMATE: ROLE_ATTENDANT,
    cc.WHAT_ESTIMATE_VERBOSE: ROLE_ATTENDANT,
    # Core reports (default user)
    cc.WHAT_OVERVIEW: ROLE_USER,
    cc.WHAT_BLOCKS: ROLE_USER,
    cc.WHAT_OVERVIEW_DOW: ROLE_USER,
    cc.WHAT_ONE_DAY: ROLE_USER,
    cc.WHAT_ONE_DAY_FREQUENCIES: ROLE_USER,
    cc.WHAT_TAGS_LOST: ROLE_USER,
    cc.WHAT_TAG_HISTORY: ROLE_USER,
    cc.WHAT_DETAIL: ROLE_USER,
    cc.WHAT_SUMMARY: ROLE_USER,
    cc.WHAT_SUMMARY_FREQUENCIES: ROLE_USER,
    cc.WHAT_COMPARE_RANGES: ROLE_USER,
    cc.WHAT_DATERANGE: ROLE_USER,
    cc.WHAT_DATERANGE_DETAIL: ROLE_USER,
    cc.WHAT_PREDICT_FUTURE: ROLE_USER,
    # Admin-only functions
    cc.WHAT_DOWNLOAD_DB: ROLE_ADMIN,
    cc.WHAT_DOWNLOAD_CSV: ROLE_ADMIN,
}

def required_role_for_what(what_code: str) -> Optional[str]:
    """Return the minimum role required for the WHAT_* code, or None if unknown."""
    return WHAT_MIN_ROLE.get(what_code)


def require_authenticated(
    env: Optional[Mapping[str, str]] = None, *, emit_header: bool = False
) -> str:
    """Ensure a valid role is present; return it or emit an error page."""
    role = get_current_role(env)
    if role is None:
        cc.error_out(
            f"{ENV_ROLE} is not set; access requires authentication.",
            emit_header=emit_header,
        )
    if not is_valid_role(role):
        cc.error_out(
            f"Unrecognized role '{cc.ut.untaint(role)}' in {ENV_ROLE}.",
            emit_header=emit_header,
        )
    return role


def require_role_for_what(
    what_code: str, env: Optional[Mapping[str, str]] = None, *, emit_header: bool = False
) -> str:
    """Ensure the caller role is allowed for the given WHAT_* code; return role."""
    role = require_authenticated(env, emit_header=emit_header)
    required = required_role_for_what(what_code)
    if required is None:
        cc.error_out(
            f"Unknown or unmapped request type '{cc.ut.untaint(what_code)}'.",
            emit_header=emit_header,
        )
    if not role_at_least(role, required):
        cc.error_out(
            f"Access denied for role '{cc.ut.untaint(role)}' to request "
            f"'{cc.ut.untaint(what_code)}'.",
            emit_header=emit_header,
        )
    return role
