from app.mango.models import CallDirection
from app.mango.parser import parse_calls


def test_parser_collects_nested_unique_recordings_and_users():
    value = {"status": "complete", "data": [{"list": [{"entry_id": "e", "context_type": 1, "context_start_time": 0,
        "caller_number": "7999", "talk_duration": 47, "context_calls": [
            {"call_type": "user", "call_abonent_info": {"name": "Иванов"}, "recording_id": ["A"],
             "members": [{"call_type": "user", "call_abonent_info": "Петров", "recording_id": ["A", "B"]}]}
        ]}]}]}
    call = parse_calls(value)[0]
    assert call.direction == CallDirection.INCOMING
    assert call.employee_names == ("Иванов", "Петров")
    assert call.recording_ids == ("A", "B")


def test_parser_tolerates_missing_fields_and_no_recording():
    call = parse_calls({"data": [{"list": [{"entry_id": "service"}]}]})[0]
    assert call.started_at is None
    assert call.recording_ids == ()


def test_parser_supports_real_mango_statistics_data_blocks():
    payload = {"status": "complete", "data": [{"list": [{
        "entry_id": "call-1", "context_type": 1,
        "context_start_time": 1786438800, "caller_number": "79991234567",
        "called_number": "74951234567", "talk_duration": 47,
        "context_calls": [{"call_type": "user", "call_abonent_info": {"name": "Иванов"},
                           "recording_id": ["recording-A"]}],
    }]}]}

    calls = parse_calls(payload)

    assert len(calls) == 1
    assert calls[0].entry_id == "call-1"
    assert calls[0].recording_ids == ("recording-A",)


def test_parser_combines_all_data_blocks_and_ignores_invalid_items():
    payload = {"status": "complete", "data": [
        {"list": [{"entry_id": "call-A"}, None]},
        "invalid block",
        {"list": [{"entry_id": "call-B"}]},
        {"list": "invalid list"},
    ]}

    calls = parse_calls(payload)

    assert [call.entry_id for call in calls] == ["call-A", "call-B"]


def test_parser_keeps_legacy_dict_envelope_tolerance():
    calls = parse_calls({"data": {"list": [{"entry_id": "legacy"}]}})

    assert [call.entry_id for call in calls] == ["legacy"]


def test_parser_extracts_employee_from_real_outbound_number_call():
    payload = {"status": "complete", "data": [{"list": [{
        "entry_id": "out-1", "context_type": 2,
        "context_calls": [{"call_type": "number", "call_abonent_info": "Иванов",
                           "recording_id": ["rec-1"]}],
    }]}]}

    assert parse_calls(payload)[0].employee_names == ("Иванов",)


def test_parser_does_not_treat_external_number_as_employee():
    payload = {"status": "complete", "data": [{"list": [{
        "entry_id": "out-2", "context_type": 2,
        "context_calls": [{"call_type": "number", "call_abonent_info": "79991234567"}],
    }]}]}

    assert parse_calls(payload)[0].employee_names == ()


def test_parser_extracts_fio_and_keeps_employee_order_unique():
    payload = {"data": [{"list": [{"entry_id": "e", "context_calls": [
        {"call_type": "user", "call_abonent_info": {"fio": "Иванов Иван"}},
        {"call_type": "number", "call_abonent_info": "Иванов Иван"},
    ]}]}]}

    assert parse_calls(payload)[0].employee_names == ("Иванов Иван",)
