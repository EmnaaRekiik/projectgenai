"""Dedicated retention worker, one per Compose deployment, no API lifecycle coupling."""

import logging
import signal
import threading

from app.core.config import get_settings
from app.db.purge_expired import purge_all_expired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
stop = threading.Event()


def _shutdown(signum, frame):
    stop.set()


def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    interval = get_settings().retention_interval_seconds
    logging.info("Retention worker starting: interval=%s seconds", interval)
    while not stop.is_set():
        try:
            logging.info("Retention results: %s", purge_all_expired())
        except Exception:
            logging.exception("Retention job failed; will retry next interval")
        stop.wait(interval)
    logging.info("Retention worker shut down")


if __name__ == "__main__":
    main()
