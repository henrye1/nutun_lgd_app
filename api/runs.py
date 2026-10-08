from __future__ import annotations

import threading
import uuid
from collections import OrderedDict

from nutun_engine.pipeline import CurveRun


class RunHolder:
    """In-memory curve runs until the run store lands (M5)."""

    def __init__(self, max_runs: int = 20):
        self._runs: OrderedDict[str, tuple[CurveRun, dict]] = OrderedDict()
        self._lock = threading.Lock()
        self.max_runs = max_runs

    def put(self, run: CurveRun, meta: dict) -> str:
        rid = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[rid] = (run, {**meta, "run_id": rid})
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
        return rid

    def replace(self, run_id: str, run: CurveRun, meta: dict) -> None:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            self._runs[run_id] = (run, {**meta, "run_id": run_id})

    def get(self, run_id: str):
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            return [meta for _, meta in self._runs.values()]

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


RUNS = RunHolder()
