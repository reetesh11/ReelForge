"""AppContext: wires settings, database, store, queue, worker and health together."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from reelforge.adapters.base import Adapter
from reelforge.adapters.llm import LlmClient
from reelforge.adapters.mock import MockAdapter
from reelforge.adapters.mock_llm import MockLlm
from reelforge.adapters.ollama import OllamaAdapter
from reelforge.artifacts.store import ArtifactStore
from reelforge.config import Settings
from reelforge.db.migrate import upgrade
from reelforge.db.models import Artifact
from reelforge.db.session import make_engine, make_session_factory
from reelforge.doctor import DoctorReport, run_doctor
from reelforge.events import EventBus
from reelforge.health import HealthMonitor
from reelforge.jobs.lease import GpuLease
from reelforge.jobs.preflight import default_available_gb
from reelforge.jobs.queue import JobQueue
from reelforge.jobs.worker import Worker
from reelforge.models_registry import ModelRegistry, load_models


class AppContext:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    registry: ModelRegistry
    store: ArtifactStore
    queue: JobQueue
    lease: GpuLease
    bus: EventBus
    worker: Worker
    health: HealthMonitor
    adapter: Adapter
    llm: LlmClient
    available_gb: Callable[[], float]
    ollama_unload: Callable[[], Awaitable[None]]
    doctor: Callable[[], DoctorReport] | None

    @classmethod
    def create(
        cls,
        settings: Settings,
        *,
        adapter: Adapter | None = None,
        available_gb: Callable[[], float] | None = None,
        ollama_unload: Callable[[], Awaitable[None]] | None = None,
        doctor: Callable[[], DoctorReport] | None = None,
        llm: LlmClient | None = None,
        migrate: bool = True,
    ) -> AppContext:
        root = settings.data_root
        for sub in ("cache/tmp", "logs/jobs", "projects"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        if migrate:
            upgrade(settings.db_path)
        self = cls()
        self.settings = settings
        self.engine = make_engine(settings.db_path)
        self.session_factory = make_session_factory(self.engine)
        self.registry = load_models(settings.models_path)
        self.bus = EventBus()
        self.store = ArtifactStore(root, self.session_factory, on_created=self._artifact_created)
        self.queue = JobQueue(self.session_factory, self.bus)
        self.lease = GpuLease(self.session_factory)
        self.adapter = adapter or MockAdapter(
            self.registry,
            default_timeout_s=settings.command_timeout_s,
            sample_interval_s=settings.sample_interval_s,
        )
        self.available_gb = available_gb or default_available_gb
        llm_model = self.registry.get("llm").id if "llm" in self.registry.keys() else None
        if ollama_unload is None:
            ollama_unload = OllamaAdapter(settings.ollama_url, llm_model).unload
        if llm is None:
            llm = (
                MockLlm()
                if settings.llm_backend == "mock"
                else OllamaAdapter(settings.ollama_url, llm_model)
            )
        self.llm = llm
        self.ollama_unload = ollama_unload
        self.doctor = doctor
        self.health = HealthMonitor(self.run_doctor, self.bus)
        self.worker = Worker(self)
        return self

    def run_doctor(self) -> DoctorReport:
        return self.doctor() if self.doctor is not None else run_doctor(self.settings)

    def _artifact_created(self, artifact: Artifact) -> None:
        self.bus.publish(
            "artifact.created",
            {
                "project_id": artifact.project_id,
                "owner_type": artifact.owner_type,
                "owner_id": artifact.owner_id,
                "kind": artifact.kind,
                "artifact_id": artifact.id,
                "take_no": artifact.take_no,
            },
        )

    def close(self) -> None:
        self.engine.dispose()
