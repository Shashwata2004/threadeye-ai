"""Roles and permissions (PLAN.md §5). Checked server-side on every endpoint via ``require(Perm.X)``."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class Role(StrEnum):
    INSPECTOR = "inspector"
    QC_SUPERVISOR = "qc_supervisor"
    STORE_INCHARGE = "store_incharge"
    CUTTING_MASTER = "cutting_master"
    MERCHANDISER = "merchandiser"
    MANAGEMENT = "management"
    ADMIN = "admin"


class Perm(StrEnum):
    # receiving
    LOTS_READ = "lots.read"
    LOTS_WRITE = "lots.write"
    ROLLS_READ = "rolls.read"
    ROLLS_WRITE = "rolls.write"
    LABELS_PRINT = "labels.print"
    MASTER_DATA_READ = "master_data.read"
    MASTER_DATA_WRITE = "master_data.write"
    # inspection
    INSPECTIONS_READ = "inspections.read"
    INSPECTIONS_RUN = "inspections.run"
    DEFECTS_CONFIRM = "defects.confirm"
    VERDICT_DECIDE = "verdict.decide"
    # evidence and decisions
    REPORTS_READ = "reports.read"
    REPORTS_GENERATE = "reports.generate"
    CLAIMS_READ = "claims.read"
    CLAIMS_WRITE = "claims.write"
    CUTTING_READ = "cutting.read"
    CUTTING_APPROVE = "cutting.approve"
    CUTTING_ACKNOWLEDGE = "cutting.acknowledge"
    SUPPLIERS_SCORECARD = "suppliers.scorecard"
    PROFILES_READ = "profiles.read"
    PROFILES_WRITE = "profiles.write"
    # oversight
    DASHBOARD_READ = "dashboard.read"
    DASHBOARD_OWN_SHIFT = "dashboard.own_shift"
    VERIFICATION_READ = "verification.read"
    VERIFICATION_RUN = "verification.run"
    BENCHMARK_READ = "benchmark.read"
    BENCHMARK_RUN = "benchmark.run"
    # administration
    PROVIDERS_MANAGE = "providers.manage"
    USERS_MANAGE = "users.manage"
    MACHINES_MANAGE = "machines.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_READ = "audit.read"
    LABEL_DATA_EXPORT = "label_data.export"


P = Perm
_READ_COMMON = {P.LOTS_READ, P.ROLLS_READ, P.MASTER_DATA_READ, P.INSPECTIONS_READ, P.VERIFICATION_READ}

ROLE_PERMS: Mapping[Role, frozenset[Perm]] = {
    Role.INSPECTOR: frozenset(
        _READ_COMMON | {P.INSPECTIONS_RUN, P.DEFECTS_CONFIRM, P.DASHBOARD_OWN_SHIFT, P.REPORTS_READ, P.PROFILES_READ}
    ),
    Role.QC_SUPERVISOR: frozenset(
        _READ_COMMON
        | {
            P.INSPECTIONS_RUN,
            P.DEFECTS_CONFIRM,
            P.VERDICT_DECIDE,
            P.REPORTS_READ,
            P.REPORTS_GENERATE,
            P.CLAIMS_READ,
            P.CUTTING_READ,
            P.CUTTING_APPROVE,
            P.SUPPLIERS_SCORECARD,
            P.PROFILES_READ,
            P.PROFILES_WRITE,
            P.DASHBOARD_READ,
            P.DASHBOARD_OWN_SHIFT,
            P.VERIFICATION_RUN,
            P.BENCHMARK_READ,
            P.BENCHMARK_RUN,
        }
    ),
    Role.STORE_INCHARGE: frozenset(
        _READ_COMMON
        | {P.LOTS_WRITE, P.ROLLS_WRITE, P.LABELS_PRINT, P.MASTER_DATA_WRITE, P.REPORTS_READ, P.PROFILES_READ}
    ),
    Role.CUTTING_MASTER: frozenset(_READ_COMMON | {P.CUTTING_READ, P.CUTTING_ACKNOWLEDGE, P.REPORTS_READ}),
    Role.MERCHANDISER: frozenset(
        _READ_COMMON
        | {
            P.REPORTS_READ,
            P.REPORTS_GENERATE,
            P.CLAIMS_READ,
            P.CLAIMS_WRITE,
            P.SUPPLIERS_SCORECARD,
            P.MASTER_DATA_WRITE,
            P.PROFILES_READ,
        }
    ),
    Role.MANAGEMENT: frozenset(
        _READ_COMMON
        | {
            P.REPORTS_READ,
            P.CLAIMS_READ,
            P.CUTTING_READ,
            P.SUPPLIERS_SCORECARD,
            P.DASHBOARD_READ,
            P.DASHBOARD_OWN_SHIFT,
            P.BENCHMARK_READ,
            P.AUDIT_READ,
            P.PROFILES_READ,
        }
    ),
    Role.ADMIN: frozenset(Perm),
}


def has_perm(role: str | Role, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMS[Role(role)]
    except ValueError:
        return False


def perms_for(role: str | Role) -> list[str]:
    try:
        return sorted(p.value for p in ROLE_PERMS[Role(role)])
    except ValueError:
        return []


DEFAULT_LOCALE: Mapping[Role, str] = {
    Role.INSPECTOR: "bn",
    Role.STORE_INCHARGE: "bn",
    Role.CUTTING_MASTER: "bn",
    Role.QC_SUPERVISOR: "en",
    Role.MERCHANDISER: "en",
    Role.MANAGEMENT: "en",
    Role.ADMIN: "en",
}
