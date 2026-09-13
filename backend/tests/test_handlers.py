from fastapi.testclient import TestClient
from verso_app.bootstrap.app import create_app
from verso_common.enums import BizCode
from verso_common.exceptions import BizException


def test_health_uses_envelope() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "success", "data": {"status": "ok"}}


def test_biz_exception_stays_http_200() -> None:
    app = create_app()

    @app.get("/_boom")
    def boom() -> None:
        raise BizException("资格已冻结", code=BizCode.FORBIDDEN)

    response = TestClient(app).get("/_boom")
    assert response.status_code == 200
    assert response.json() == {
        "code": 403,
        "message": "资格已冻结",
        "data": None,
    }


def test_validation_error_uses_first_message() -> None:
    app = create_app()

    @app.get("/_need")
    def need(q: int) -> dict[str, int]:
        return {"q": q}

    response = TestClient(app).get("/_need")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 400
    assert body["data"]
