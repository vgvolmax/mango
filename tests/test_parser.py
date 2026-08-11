from app.mango.models import CallDirection
from app.mango.parser import parse_calls


def test_parser_collects_nested_unique_recordings_and_users():
    value = {"data": {"list": [{"entry_id": "e", "context_type": 1, "context_start_time": 0,
        "caller_number": "7999", "talk_duration": 47, "context_calls": [
            {"call_type": "user", "call_abonent_info": {"name": "Иванов"}, "recording_id": ["A"],
             "members": [{"call_type": "user", "call_abonent_info": "Петров", "recording_id": ["A", "B"]}]}
        ]}]}}
    call = parse_calls(value)[0]
    assert call.direction == CallDirection.INCOMING
    assert call.employee_names == ("Иванов", "Петров")
    assert call.recording_ids == ("A", "B")


def test_parser_tolerates_missing_fields_and_no_recording():
    call = parse_calls({"data": {"list": [{"entry_id": "service"}]}})[0]
    assert call.started_at is None
    assert call.recording_ids == ()
