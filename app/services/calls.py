"""Polling and pagination for call statistics."""

import logging
import time
from datetime import datetime

from app.mango.errors import MangoApiError, MangoStatisticsTimeout
from app.mango.parser import parse_calls


class CallService:
    PAGE_SIZE = 5000

    def __init__(self, client, *, poll_interval: float = 3, poll_timeout: float = 90, clock=time.monotonic, sleep=time.sleep) -> None:
        self.client, self.poll_interval, self.poll_timeout = client, poll_interval, poll_timeout
        self.clock, self.sleep = clock, sleep

    def get_calls(self, start: datetime, end: datetime):
        records, offset = [], 0
        while True:
            key = self.client.request_statistics({"start_date": start.strftime("%d.%m.%Y %H:%M:%S"), "end_date": end.strftime("%d.%m.%Y %H:%M:%S"), "limit": self.PAGE_SIZE, "offset": offset})
            deadline = self.clock() + self.poll_timeout
            while True:
                value = self.client.statistics_result(key)
                state = str(value.get("status") or value.get("state") or "complete").lower()
                if state == "complete":
                    break
                if state not in {"request", "work"}:
                    raise MangoApiError(f"Statistics failed: {state}")
                if self.clock() >= deadline:
                    raise MangoStatisticsTimeout("Statistics polling timed out")
                self.sleep(self.poll_interval)
            page = parse_calls(value)
            records.extend(page)
            if len(page) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        logging.getLogger(__name__).info("Found %d calls and %d recording IDs", len(records), sum(len(x.recording_ids) for x in records))
        return records
