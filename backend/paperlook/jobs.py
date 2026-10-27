"""In-process background jobs with persisted status.

Every long operation (recommendation run, full-text fetch, translation, AI analysis) is a Job.
The UI polls job status. Submitting the same (kind, paper) while one is active returns the
existing job - so a double click can never trigger two paid API calls.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import db
from .errors import AppError

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")


class JobCancelled(Exception):
    pass


class Job:
    def __init__(self, kind: str, paper_id: str | None, meta: dict[str, Any] | None = None):
        self.id = uuid.uuid4().hex[:16]
        self.kind = kind
        self.paper_id = paper_id
        self.status = "queued"
        self.progress = 0
        self.total = 0
        self.message = "排队中…"
        self.error: str | None = None
        self.error_code: str | None = None
        self.result: Any = None
        self.meta = meta or {}
        self.created_at = db.now_iso()
        self.updated_at = self.created_at
        self._cancel = threading.Event()
        self._last_persist = 0.0
        self._lock = threading.Lock()
        self._final_message = False

    # -- progress API used by workers --
    def update(self, *, progress: int | None = None, total: int | None = None, message: str | None = None,
               force: bool = False) -> None:
        with self._lock:
            if progress is not None:
                self.progress = progress
            if total is not None:
                self.total = total
            if message is not None:
                self.message = message
            self.updated_at = db.now_iso()
        if force or time.monotonic() - self._last_persist > 1.0:
            self.persist()

    def advance(self, n: int = 1, message: str | None = None) -> None:
        with self._lock:
            self.progress += n
        self.update(message=message)

    def finish(self, message: str, status: str | None = None) -> None:
        """Set the message shown after the job ends (and optionally a non-'done' final status)."""
        self.message = message
        self._final_message = True
        if status:
            self.status = status

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()

    def persist(self) -> None:
        self._last_persist = time.monotonic()
        db.execute(
            "INSERT INTO jobs(id, kind, paper_id, status, progress, total, message, error, result, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, progress=excluded.progress, "
            "total=excluded.total, message=excluded.message, error=excluded.error, result=excluded.result, updated_at=excluded.updated_at",
            (self.id, self.kind, self.paper_id, self.status, self.progress, self.total, self.message,
             db.dumps({"message": self.error, "code": self.error_code}) if self.error else None,
             db.dumps(self.result) if self.result is not None else None, self.created_at, self.updated_at),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "paper_id": self.paper_id, "status": self.status,
            "progress": self.progress, "total": self.total, "message": self.message,
            "error": self.error, "error_code": self.error_code, "result": self.result, "meta": self.meta,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


def _row_to_dict(r: dict[str, Any]) -> dict[str, Any]:
    err = db.loads(r.get("error"), None)
    if isinstance(err, str):
        err = {"message": err, "code": None}
    return {
        "id": r["id"], "kind": r["kind"], "paper_id": r["paper_id"], "status": r["status"],
        "progress": r["progress"], "total": r["total"], "message": r["message"],
        "error": (err or {}).get("message"), "error_code": (err or {}).get("code"),
        "result": db.loads(r.get("result"), None), "meta": {},
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


class JobManager:
    def __init__(self, workers: int = 6):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def recover_after_restart(self) -> None:
        db.execute("UPDATE jobs SET status='interrupted', message='应用重启，任务已中断' WHERE status IN ('queued','running')")
        # keep the table small
        db.execute("DELETE FROM jobs WHERE datetime(created_at) < datetime('now', '-30 days')")

    def find_active(self, kind: str, paper_id: str | None) -> Job | None:
        with self._lock:
            for j in self._jobs.values():
                if j.kind == kind and j.paper_id == paper_id and j.status in ACTIVE:
                    return j
        return None

    def submit(self, kind: str, fn: Callable[[Job], Any], paper_id: str | None = None,
               meta: dict[str, Any] | None = None) -> Job:
        with self._lock:
            for j in self._jobs.values():
                if j.kind == kind and j.paper_id == paper_id and j.status in ACTIVE:
                    return j
            job = Job(kind, paper_id, meta)
            self._jobs[job.id] = job
        job.persist()
        self._executor.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[Job], Any]) -> None:
        job.status = "running"
        job.update(message="正在处理…", force=True)
        try:
            result = fn(job)
            job.result = result
            if job.status == "running":
                job.status = "done"
            if not job._final_message:
                job.message = "已完成"
        except JobCancelled:
            job.status = "cancelled"
            job.message = "已停止"
        except AppError as e:
            job.status = "failed"
            job.error = e.message
            job.error_code = e.code
            job.message = "失败"
        except Exception as e:  # unexpected - log with traceback, show a short message
            log.error("Job %s (%s) crashed: %s\n%s", job.id, job.kind, e, traceback.format_exc())
            job.status = "failed"
            job.error = f"内部错误：{type(e).__name__}: {e}"
            job.error_code = "internal"
            job.message = "失败"
        finally:
            job.updated_at = db.now_iso()
            try:
                job.persist()
            except Exception:
                log.exception("Failed to persist job %s", job.id)
            self._prune()

    def _prune(self) -> None:
        with self._lock:
            finished = [j for j in self._jobs.values() if j.status not in ACTIVE]
            if len(finished) > 200:
                finished.sort(key=lambda j: j.updated_at)
                for j in finished[:-100]:
                    self._jobs.pop(j.id, None)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            j = self._jobs.get(job_id)
        if j:
            return j.to_dict()
        r = db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _row_to_dict(r) if r else None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            j = self._jobs.get(job_id)
        if j and j.status in ACTIVE:
            j.cancel()
            return True
        return False

    def active(self, paper_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()
                    if j.status in ACTIVE and (paper_id is None or j.paper_id == paper_id)]

    def latest(self, kind: str, paper_id: str | None) -> dict[str, Any] | None:
        with self._lock:
            mem = [j for j in self._jobs.values() if j.kind == kind and j.paper_id == paper_id]
        if mem:
            return max(mem, key=lambda j: j.created_at).to_dict()
        if paper_id is None:
            r = db.query_one("SELECT * FROM jobs WHERE kind = ? AND paper_id IS NULL ORDER BY created_at DESC LIMIT 1", (kind,))
        else:
            r = db.query_one("SELECT * FROM jobs WHERE kind = ? AND paper_id = ? ORDER BY created_at DESC LIMIT 1",
                             (kind, paper_id))
        return _row_to_dict(r) if r else None


manager = JobManager()
