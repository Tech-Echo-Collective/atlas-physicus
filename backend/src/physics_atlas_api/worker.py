import argparse
import logging
import time
from functools import partial
from pathlib import Path

from .config import get_settings
from .connectors.factory import build_connectors
from .database import SessionLocal
from .logging_config import configure_logging
from .resources.monitor import (
    HttpResourceTransport,
    ResourceMonitor,
    validate_resource_url,
)
from .scheduler import SOURCE_CADENCE, UpdateScheduler
from .seed import ensure_reference_data
from .updates import IncrementalUpdateEngine

logger = logging.getLogger("physics_atlas_api.worker")


def execute_once(
    source: str = "all",
    *,
    fixture_directory: Path | None = None,
    check_resources: bool = False,
) -> int:
    settings = get_settings()
    connectors = build_connectors(settings, fixture_directory)
    requested = list(SOURCE_CADENCE) if source == "all" else [source]
    with SessionLocal() as session:
        ensure_reference_data(session)
        scheduler = UpdateScheduler(session)
        if not scheduler.acquire_lock():
            logger.warning(
                "worker lock is held",
                extra={"event": "worker.locked", "source": source},
            )
            return 0
        failures = 0
        try:
            for provider in scheduler.due_sources(requested):
                result = IncrementalUpdateEngine(session, connectors[provider]).run()
                failures += int(result.status != "succeeded")
            if check_resources:
                monitor_result = ResourceMonitor(
                    session,
                    HttpResourceTransport(),
                    timeout_seconds=settings.provider_timeout_seconds,
                    url_validator=partial(
                        validate_resource_url,
                        allowed_hosts=settings.resource_allowed_hosts,
                    ),
                ).run(limit=settings.resource_check_max_per_run)
                logger.info(
                    "resource monitor completed",
                    extra={
                        "event": "resources.completed",
                        "records": monitor_result.checked,
                    },
                )
        finally:
            scheduler.release_lock()
        return failures


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Physics Atlas incremental update worker"
    )
    parser.add_argument(
        "--source",
        choices=["all", "inspire", "arxiv", "ror"],
        default="all",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-resources", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.once:
        raise SystemExit(
            execute_once(args.source, check_resources=args.check_resources)
        )
    while True:
        execute_once(args.source, check_resources=args.check_resources)
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
