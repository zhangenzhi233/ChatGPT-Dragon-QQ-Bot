"""Expression routes pytest tests"""

from types import SimpleNamespace
from typing import Generator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from src.common.database.database_model import Expression, ModifiedBy
from src.webui.dependencies import require_auth
from src.webui.routers.expression import parse_modified_by


def create_test_app() -> FastAPI:
    """Create minimal test app with only expression router"""
    app = FastAPI(title="Test App")
    from src.webui.routers.expression import router as expression_router

    main_router = APIRouter(prefix="/api/webui")
    main_router.include_router(expression_router)
    app.include_router(main_router)

    return app


app = create_test_app()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("AI", ModifiedBy.AI),
        ("ai", ModifiedBy.AI),
        ('"AI"', ModifiedBy.AI),
        ("USER", ModifiedBy.USER),
        ("user", ModifiedBy.USER),
        ('"user"', ModifiedBy.USER),
        ("unknown", None),
    ],
)
def test_parse_modified_by_normalizes_legacy_values(raw_value: str, expected: ModifiedBy | None):
    """Test modified_by import parser normalizes legacy AI/USER values."""
    assert parse_modified_by(raw_value) == expected


# Test database setup
@pytest.fixture(name="test_engine")
def test_engine_fixture():
    """Create in-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="test_session")
def test_session_fixture(test_engine) -> Generator[Session, None, None]:
    """Create a test database session with transaction rollback"""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(name="client")
def client_fixture(test_session: Session, monkeypatch) -> Generator[TestClient, None, None]:
    """Create TestClient with overridden database session"""
    from contextlib import contextmanager

    @contextmanager
    def get_test_db_session():
        yield test_session
        test_session.commit()

    monkeypatch.setattr("src.webui.routers.expression.get_db_session", get_test_db_session)

    with TestClient(app) as client:
        yield client


@pytest.fixture(name="mock_auth")
def mock_auth_fixture():
    """Mock authentication to always return True"""
    app.dependency_overrides[require_auth] = lambda: "test-token"
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_existing_chat_stream(monkeypatch):
    """Mock chat manager lookups so resource ownership checks can pass in route tests."""
    monkeypatch.setattr(
        "src.webui.routers.expression._chat_manager.get_existing_session_by_session_id",
        lambda chat_id: SimpleNamespace(session_id=chat_id),
    )


@pytest.fixture(name="sample_expression")
def sample_expression_fixture(test_session: Session) -> Expression:
    """Insert a sample expression into test database"""
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (1, '测试情景', '测试风格', '[\"测试内容1\", \"测试内容2\"]', 10, '2026-02-17 12:00:00', '2026-02-15 10:00:00', 'test_chat_001', 0)"
        )
    )
    test_session.commit()

    expression = test_session.exec(select(Expression).where(Expression.id == 1)).first()
    assert expression is not None
    return expression


# ============ Tests ============


def test_list_expressions_empty(client: TestClient, mock_auth):
    """Test GET /expression/list with empty database"""
    response = client.get("/api/webui/expression/list?include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["data"] == []


def test_list_expressions_with_data(client: TestClient, mock_auth, sample_expression: Expression):
    """Test GET /expression/list returns expression data"""
    response = client.get("/api/webui/expression/list?include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["data"]) == 1

    expr_data = data["data"][0]
    assert expr_data["id"] == sample_expression.id
    assert expr_data["situation"] == "测试情景"
    assert expr_data["style"] == "测试风格"
    assert expr_data["chat_id"] == "test_chat_001"


def test_list_expressions_pagination(client: TestClient, mock_auth, test_session: Session):
    """Test GET /expression/list pagination works correctly"""
    for i in range(5):
        test_session.execute(
            text(
                f"INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
                f"VALUES ({i + 1}, '情景{i}', '风格{i}', '[]', 0, '2026-02-17 12:0{i}:00', '2026-02-15 10:00:00', 'chat_{i}', 0)"
            )
        )
    test_session.commit()

    # Request page 1 with page_size=2
    response = client.get("/api/webui/expression/list?page=1&page_size=2&include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["data"]) == 2

    # Request page 2
    response = client.get("/api/webui/expression/list?page=2&page_size=2&include_legacy=true")
    data = response.json()
    assert data["page"] == 2
    assert len(data["data"]) == 2


def test_list_expressions_search(client: TestClient, mock_auth, test_session: Session):
    """Test GET /expression/list with search filter"""
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (1, '找人吃饭', '热情', '[]', 0, datetime('now'), datetime('now'), 'chat_001', 0)"
        )
    )
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (2, '拒绝邀请', '礼貌', '[]', 0, datetime('now'), datetime('now'), 'chat_002', 0)"
        )
    )
    test_session.commit()

    # Search for "吃饭"
    response = client.get("/api/webui/expression/list?search=吃饭&include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["situation"] == "找人吃饭"


def test_list_expressions_chat_filter(client: TestClient, mock_auth, test_session: Session):
    """Test GET /expression/list with chat_id filter"""
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (1, '情景A', '风格A', '[]', 0, datetime('now'), datetime('now'), 'chat_A', 0)"
        )
    )
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (2, '情景B', '风格B', '[]', 0, datetime('now'), datetime('now'), 'chat_B', 0)"
        )
    )
    test_session.commit()

    # Filter by chat_A
    response = client.get("/api/webui/expression/list?chat_id=chat_A&include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["situation"] == "情景A"
    assert data["data"][0]["chat_id"] == "chat_A"


def test_get_expression_detail_success(client: TestClient, mock_auth, sample_expression: Expression):
    """Test GET /expression/{id} returns correct detail"""
    response = client.get(f"/api/webui/expression/{sample_expression.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["id"] == sample_expression.id
    assert data["data"]["situation"] == "测试情景"
    assert data["data"]["style"] == "测试风格"
    assert data["data"]["chat_id"] == "test_chat_001"


def test_get_expression_detail_not_found(client: TestClient, mock_auth):
    """Test GET /expression/{id} returns 404 for non-existent ID"""
    response = client.get("/api/webui/expression/99999")
    assert response.status_code == 404

    data = response.json()
    assert "未找到" in data["detail"]


def test_expression_response_has_review_fields(client: TestClient, mock_auth, sample_expression: Expression):
    """Test that ExpressionResponse includes current review fields."""
    response = client.get(f"/api/webui/expression/{sample_expression.id}")
    assert response.status_code == 200

    data = response.json()["data"]

    assert "checked" in data
    assert "modified_by" in data

    assert data["checked"] is False
    assert data["modified_by"] is None


def test_update_expression_without_removed_fields(client: TestClient, mock_auth, sample_expression: Expression):
    """Test PATCH /expression/{id} does not accept removed review fields."""
    # Valid update request (only allowed fields)
    update_payload = {
        "situation": "更新后的情景",
        "style": "更新后的风格",
    }

    response = client.patch(f"/api/webui/expression/{sample_expression.id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["situation"] == "更新后的情景"
    assert data["data"]["style"] == "更新后的风格"

    assert data["data"]["checked"] is False


def test_update_expression_ignores_invalid_fields(client: TestClient, mock_auth, sample_expression: Expression):
    """Test PATCH /expression/{id} ignores fields not in ExpressionUpdateRequest"""
    # Request with invalid field (checked not in schema)
    update_payload = {
        "situation": "新情景",
        "checked": True,  # This field should be ignored by Pydantic
        "removed_review_state": True,  # This removed field should be ignored
    }

    response = client.patch(f"/api/webui/expression/{sample_expression.id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["situation"] == "新情景"

    assert data["data"]["checked"] is False


def test_update_expression_chat_id_mapping(client: TestClient, mock_auth, sample_expression: Expression):
    """Test PATCH /expression/{id} correctly maps chat_id to session_id"""
    update_payload = {"chat_id": "updated_chat_999"}

    response = client.patch(f"/api/webui/expression/{sample_expression.id}", json=update_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True

    # Verify chat_id is returned in response (mapped from session_id)
    assert data["data"]["chat_id"] == "updated_chat_999"


def test_update_expression_not_found(client: TestClient, mock_auth):
    """Test PATCH /expression/{id} returns 404 for non-existent ID"""
    update_payload = {"situation": "新情景"}

    response = client.patch("/api/webui/expression/99999", json=update_payload)
    assert response.status_code == 404

    data = response.json()
    assert "未找到" in data["detail"]


def test_update_expression_empty_request(client: TestClient, mock_auth, sample_expression: Expression):
    """Test PATCH /expression/{id} returns 400 for empty update request"""
    update_payload = {}

    response = client.patch(f"/api/webui/expression/{sample_expression.id}", json=update_payload)
    assert response.status_code == 400

    data = response.json()
    assert "未提供任何需要更新的字段" in data["detail"]


def test_delete_expression_success(client: TestClient, mock_auth, sample_expression: Expression):
    """Test DELETE /expression/{id} successfully deletes expression"""
    expression_id = sample_expression.id

    response = client.delete(f"/api/webui/expression/{expression_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert "成功删除" in data["message"]

    # Verify expression is deleted
    get_response = client.get(f"/api/webui/expression/{expression_id}")
    assert get_response.status_code == 404


def test_delete_expression_not_found(client: TestClient, mock_auth):
    """Test DELETE /expression/{id} returns 404 for non-existent ID"""
    response = client.delete("/api/webui/expression/99999")
    assert response.status_code == 404

    data = response.json()
    assert "未找到" in data["detail"]


def test_create_expression_success(client: TestClient, mock_auth):
    """Test POST /expression/ successfully creates expression"""
    create_payload = {
        "situation": "新建情景",
        "style": "新建风格",
        "chat_id": "new_chat_123",
    }

    response = client.post("/api/webui/expression/", json=create_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert "创建成功" in data["message"]
    assert data["data"]["situation"] == "新建情景"
    assert data["data"]["style"] == "新建风格"
    assert data["data"]["chat_id"] == "new_chat_123"

    assert data["data"]["checked"] is False
    assert data["data"]["modified_by"] is None


def test_batch_delete_expressions_success(client: TestClient, mock_auth, test_session: Session):
    """Test POST /expression/batch/delete successfully deletes multiple expressions"""
    expression_ids = []
    for i in range(3):
        test_session.execute(
            text(
                f"INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
                f"VALUES ({i + 1}, '批量删除{i}', '风格{i}', '[]', 0, datetime('now'), datetime('now'), 'chat_{i}', 0)"
            )
        )
        expression_ids.append(i + 1)
    test_session.commit()

    delete_payload = {"ids": expression_ids}
    response = client.post("/api/webui/expression/batch/delete", json=delete_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert "成功删除 3 个" in data["message"]

    for expr_id in expression_ids:
        get_response = client.get(f"/api/webui/expression/{expr_id}")
        assert get_response.status_code == 404


def test_batch_delete_partial_not_found(client: TestClient, mock_auth, sample_expression: Expression):
    """Test POST /expression/batch/delete handles partial not found IDs"""
    delete_payload = {"ids": [sample_expression.id, 88888, 99999]}

    response = client.post("/api/webui/expression/batch/delete", json=delete_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    # Should delete only the 1 valid ID
    assert "成功删除 1 个" in data["message"]


def test_get_expression_stats(client: TestClient, mock_auth, test_session: Session):
    """Test GET /expression/stats/summary returns correct statistics"""
    for i in range(3):
        test_session.execute(
            text(
                f"INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
                f"VALUES ({i + 1}, '情景{i}', '风格{i}', '[]', 0, datetime('now'), datetime('now'), 'chat_{i % 2}', 0)"
            )
        )
    test_session.commit()

    response = client.get("/api/webui/expression/stats/summary?include_legacy=true")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["total"] == 3
    assert data["data"]["chat_count"] == 2


def test_get_review_stats(client: TestClient, mock_auth, test_session: Session):
    """Test GET /expression/review/stats returns review status counts"""
    test_session.execute(
        text(
            "INSERT INTO expressions (id, situation, style, content_list, count, last_active_time, create_time, session_id, checked) "
            "VALUES (1, '待审核', '风格', '[]', 0, datetime('now'), datetime('now'), 'chat_001', 0)"
        )
    )
    test_session.commit()

    response = client.get("/api/webui/expression/review/stats")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1  # Total expressions exists
    assert data["unchecked"] == 1
    assert data["passed"] == 0
    assert data["ai_checked"] == 0
    assert data["user_checked"] == 0


def test_get_review_list_filter_unchecked(client: TestClient, mock_auth, sample_expression: Expression):
    """Test GET /expression/review/list with filter_type=unchecked returns unchecked expressions"""
    response = client.get("/api/webui/expression/review/list?filter_type=unchecked")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["data"]) == 1


def test_get_review_list_filter_all(client: TestClient, mock_auth, sample_expression: Expression):
    """Test GET /expression/review/list with filter_type=all returns all expressions"""
    response = client.get("/api/webui/expression/review/list?filter_type=all")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert len(data["data"]) == 1


def test_batch_review_expressions_with_unchecked_marker(client: TestClient, mock_auth, sample_expression: Expression):
    """Test POST /expression/review/batch succeeds with require_unchecked=True"""
    review_payload = {"items": [{"id": sample_expression.id, "approved": True, "require_unchecked": True}]}

    response = client.post("/api/webui/expression/review/batch", json=review_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["succeeded"] == 1
    assert data["results"][0]["success"] is True


def test_batch_review_reject_deletes_expression(
    client: TestClient, mock_auth, test_session: Session, sample_expression: Expression
):
    """Test POST /expression/review/batch deletes expressions not approved by manual review."""
    review_payload = {"items": [{"id": sample_expression.id, "approved": False, "require_unchecked": True}]}

    response = client.post("/api/webui/expression/review/batch", json=review_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["succeeded"] == 1
    test_session.expire_all()
    reviewed_expression = test_session.exec(select(Expression).where(Expression.id == sample_expression.id)).first()
    assert reviewed_expression is None


def test_batch_review_expressions_overwrites_ai_checked(
    client: TestClient, mock_auth, test_session: Session, sample_expression: Expression
):
    """Test POST /expression/review/batch lets manual review override AI checked state"""
    sample_expression.checked = True
    sample_expression.modified_by = ModifiedBy.AI
    test_session.add(sample_expression)
    test_session.commit()

    review_payload = {"items": [{"id": sample_expression.id, "approved": True, "require_unchecked": True}]}

    response = client.post("/api/webui/expression/review/batch", json=review_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["succeeded"] == 1
    test_session.expire_all()
    reviewed_expression = test_session.exec(select(Expression).where(Expression.id == sample_expression.id)).first()
    assert reviewed_expression is not None
    assert reviewed_expression.checked is True
    assert reviewed_expression.modified_by == ModifiedBy.USER


def test_batch_review_expressions_no_unchecked_check(client: TestClient, mock_auth, sample_expression: Expression):
    """Test POST /expression/review/batch succeeds when require_unchecked=False"""
    review_payload = {"items": [{"id": sample_expression.id, "approved": True, "require_unchecked": False}]}

    response = client.post("/api/webui/expression/review/batch", json=review_payload)
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["succeeded"] == 1
    assert data["results"][0]["success"] is True


def test_get_expression_review_logs_reads_json_file(client: TestClient, mock_auth, tmp_path, monkeypatch):
    """Test GET /expression/review/logs returns recent AI review records from JSON."""
    import src.learners.expression_review_store as review_store

    monkeypatch.setattr(review_store, "REVIEW_LOG_PATH", tmp_path / "expression_review" / "review_logs.json")
    review_store.append_ai_review_log(
        session_id="chat_json",
        situation="表示惊讶",
        style="使用 好家伙",
        passed=False,
        reason="表达方式过于特定",
        source="learn_before_upsert",
    )

    response = client.get("/api/webui/expression/review/logs")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["data"][0]["session_id"] == "chat_json"
    assert data["data"][0]["passed"] is False
    assert data["data"][0]["reason"] == "表达方式过于特定"


def test_get_expression_review_logs_filters_by_chat_id(client: TestClient, mock_auth, tmp_path, monkeypatch):
    """Test GET /expression/review/logs filters AI review records by chat_id."""
    import src.learners.expression_review_store as review_store

    monkeypatch.setattr(review_store, "REVIEW_LOG_PATH", tmp_path / "expression_review" / "review_logs.json")
    review_store.append_ai_review_log(
        session_id="chat_a",
        situation="表示惊讶",
        style="使用 好家伙",
        passed=False,
        reason="表达方式过于特定",
        source="learn_before_upsert",
    )
    review_store.append_ai_review_log(
        session_id="chat_b",
        situation="表示赞同",
        style="使用 确实",
        passed=True,
        reason="表达方式可用",
        source="learn_before_upsert",
    )

    response = client.get("/api/webui/expression/review/logs?chat_id=chat_b")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["data"][0]["session_id"] == "chat_b"
    assert data["data"][0]["situation"] == "表示赞同"


def test_approve_expression_review_log_restores_deleted_expression(
    client: TestClient,
    mock_auth,
    test_session: Session,
    tmp_path,
    monkeypatch,
):
    """Test POST /expression/review/logs/{id}/approve restores a rejected expression as user-approved."""
    import src.learners.expression_review_store as review_store

    monkeypatch.setattr(review_store, "REVIEW_LOG_PATH", tmp_path / "expression_review" / "review_logs.json")
    review_entry = review_store.append_ai_review_log(
        session_id="chat_restore",
        situation="想吐槽时",
        style="使用 什么情况",
        passed=False,
        reason="AI 误判",
        source="learn_before_upsert",
        expression_id=12345,
    )

    response = client.post(f"/api/webui/expression/review/logs/{review_entry['id']}/approve")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["checked"] is True
    assert data["data"]["modified_by"] == "user"
    assert data["data"]["chat_id"] == "chat_restore"

    test_session.expire_all()
    restored_expression = test_session.exec(select(Expression).where(Expression.session_id == "chat_restore")).first()
    assert restored_expression is not None
    assert restored_expression.checked is True
    assert restored_expression.modified_by == ModifiedBy.USER
