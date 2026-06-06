from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any, Callable
from uuid import uuid4


@dataclass
class Job:
    id: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    cancelled: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobManager:
    def __init__(self, max_workers: int = 1) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs: dict[str, Job] = {}
        self.lock = Lock()

    def submit(self, func: Callable[..., Any], *args, **kwargs) -> str:
        job_id = uuid4().hex
        job = Job(id=job_id)
        with self.lock:
            self.jobs[job_id] = job

        def progress(value: int, message: str = "") -> None:
            with self.lock:
                current = self.jobs[job_id]
                current.progress = max(0, min(100, int(value)))
                current.message = message or current.message
                current.updated_at = time()

        def runner() -> None:
            with self.lock:
                job.status = "running"
                job.progress = 5
                job.message = "Running"
                job.updated_at = time()
            try:
                result = func(*args, progress=progress, **kwargs)
                with self.lock:
                    job.result = result
                    job.status = "complete"
                    job.progress = 100
                    job.message = "Complete"
                    job.updated_at = time()
            except Exception as exc:
                with self.lock:
                    job.status = "error"
                    job.error = str(exc)
                    job.message = "Error"
                    job.updated_at = time()

        self.executor.submit(runner)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return job.public() if job else None

