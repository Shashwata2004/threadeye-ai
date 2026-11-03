"""Optional demo reset by archiving SAMPLE deliveries; evidence and audit records are retained."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.db import audit
from threadeye.db.models import Inspection, Lot, Roll, Setting, User
from threadeye.db.session import get_sessionmaker
from threadeye.security.rbac import Perm, has_perm
from threadeye.services import live


def archive(db: Session, actor: User) -> int:
    lots = list(db.scalars(select(Lot).where(Lot.is_sample_data.is_(True), Lot.status != "archived").with_for_update()))
    ids = [lot.id for lot in lots]
    if ids:
        inspections = list(
            db.scalars(
                select(Inspection)
                .join(Roll, Roll.id == Inspection.roll_id)
                .where(Roll.lot_id.in_(ids), Inspection.status.in_(live.OPEN))
                .with_for_update(of=Inspection)
            )
        )
        for inspection in inspections:
            live.abort(db, inspection, actor, f"archive-{inspection.id}", None)
        for lot in lots:
            lot.status = "archived"
        audit.record(
            db,
            action="demo.archive",
            actor_user_id=actor.id,
            actor_role=actor.role,
            entity_type="demo",
            entity_id="sample_deliveries",
            after={"lot_ids": [str(id_) for id_ in ids]},
        )
    return len(lots)


def scheduled(at: datetime | None = None) -> None:
    now = (at or datetime.now(ZoneInfo("Asia/Dhaka"))).astimezone(ZoneInfo("Asia/Dhaka"))
    with get_sessionmaker()() as db:
        setting = db.scalar(select(Setting).where(Setting.key == "demo_archive_schedule").with_for_update())
        if not setting or not setting.value.get("enabled") or now.hour < 3:
            return
        value = dict(setting.value)
        today = str(now.date())
        if today < value["start_date"] or value.get("last_date") == today or not setting.updated_by:
            return
        actor = db.get(User, setting.updated_by)
        if not actor or not actor.active or not has_perm(actor.role, Perm.SETTINGS_MANAGE):
            return
        archive(db, actor)
        setting.value = {**value, "last_date": today}
        db.commit()
