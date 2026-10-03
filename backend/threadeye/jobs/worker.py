"""Background worker (edge profile). ``python -m threadeye.jobs.worker``.

M0: writes a heartbeat every few seconds so the dashboard can show the worker is alive.
From M4/M5: Postgres-backed job queue (MP4 clips, PDFs, daily verification, benchmarks) and, later,
the server-clocked webcam runner.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import UTC, datetime
from types import FrameType

from sqlalchemy.dialects.postgresql import insert

from threadeye import __version__
from threadeye.db.models import ComponentHeartbeat
from threadeye.db.session import get_sessionmaker

log = logging.getLogger("threadeye.worker")
HEARTBEAT_SECONDS = 5.0


class Worker:
    def __init__(self) -> None:
        self._stop = False

    def stop(self, signum: int, _frame: FrameType | None) -> None:
        log.info("signal %s received, stopping", signum)
        self._stop = True

    def heartbeat(self) -> None:
        now = datetime.now(UTC)
        details = {"version": __version__, "queue": "not used before M4"}
        stmt = insert(ComponentHeartbeat).values(component="worker", last_seen_at=now, details=details)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ComponentHeartbeat.component],
            set_={"last_seen_at": now, "details": details},
        )
        with get_sessionmaker()() as db:
            db.execute(stmt)
            db.commit()

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        log.info("worker started (version %s)", __version__)
        while not self._stop:
            try:
                self.heartbeat()
            except Exception:
                log.exception("heartbeat failed; retrying")
            deadline = time.monotonic() + HEARTBEAT_SECONDS
            while not self._stop and time.monotonic() < deadline:
                time.sleep(0.2)
        log.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Worker().run()


if __name__ == "__main__":
    main()
