from datetime import datetime

from app.services.calls import CallService


class StatisticsClient:
    def request_statistics(self, parameters):
        return "request-key"

    def statistics_result(self, key):
        assert key == "request-key"
        return {"status": "complete", "data": [{"list": [{
            "entry_id": "real-call", "context_type": 1,
            "context_start_time": 1786438800,
            "context_calls": [{"recording_id": ["recording-A"]}],
        }]}]}


def test_get_calls_parses_real_mango_statistics_envelope():
    calls = CallService(StatisticsClient()).get_calls(datetime(2026, 1, 1), datetime(2026, 1, 2))

    assert len(calls) == 1
    assert calls[0].entry_id == "real-call"
    assert calls[0].recording_ids == ("recording-A",)


class PaginatedStatisticsClient:
    def __init__(self):
        self.parameters = []

    def request_statistics(self, parameters):
        self.parameters.append(parameters)
        return len(self.parameters) - 1

    def statistics_result(self, key):
        pages = [
            {"status": "complete", "data": [
                {"list": [{"entry_id": "call-1"}]},
                {"list": [{"entry_id": "call-2"}]},
            ]},
            {"status": "complete", "data": [
                {"list": [{"entry_id": "call-3"}, "invalid entry"]},
            ]},
        ]
        return pages[key]


def test_get_calls_paginates_by_extracted_logical_call_count():
    client = PaginatedStatisticsClient()
    service = CallService(client)
    service.PAGE_SIZE = 2

    calls = service.get_calls(datetime(2026, 1, 1), datetime(2026, 1, 2))

    assert [call.entry_id for call in calls] == ["call-1", "call-2", "call-3"]
    assert [parameters["limit"] for parameters in client.parameters] == [2, 2]
    assert [parameters["offset"] for parameters in client.parameters] == [0, 2]
