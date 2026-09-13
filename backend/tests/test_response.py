from datetime import UTC, datetime

from verso_common.enums import (
    BizCode,
    Eligibility,
    ExchangeStatus,
    PortraitHorizon,
    ReviewVerdict,
    MatchConditionStatus,
    StrengthTag,
)
from verso_common.result import ListResponse, Response


def test_domain_enums_match_spec() -> None:
    assert StrengthTag.PROGRAMMING == "编程"
    assert StrengthTag.FITNESS == "健身"
    assert MatchConditionStatus.WAITING == "waiting"
    assert ExchangeStatus.CLOSED == "closed"
    assert ReviewVerdict.POOR == "poor"
    assert Eligibility.SUSPENDED == "suspended"
    assert PortraitHorizon.RECENT_7D == "recent_7d"


def test_response_success_omits_null_timestamp() -> None:
    payload = Response.success({"id": "u1"}).model_dump(mode="json")
    assert payload == {"code": 200, "message": "success", "data": {"id": "u1"}}
    assert "timestamp" not in payload


def test_response_fail_keeps_null_data() -> None:
    payload = Response.fail("用户不存在", code=BizCode.NOT_FOUND).model_dump(mode="json")
    assert payload == {"code": 404, "message": "用户不存在", "data": None}


def test_response_can_carry_timestamp() -> None:
    ts = datetime(2026, 9, 13, 12, 0, 0, tzinfo=UTC)
    payload = Response.success("ok", timestamp=ts).model_dump(mode="json")
    assert payload["timestamp"] == "2026-09-13T12:00:00Z"


def test_list_response_defaults_total_to_len() -> None:
    payload = ListResponse.success(["a", "b"], page=1, page_size=0).model_dump(mode="json")
    assert payload["total"] == 2
    assert payload["data"] == ["a", "b"]
    assert payload["page_size"] == 0
