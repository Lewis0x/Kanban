def test_cached_queries_route(client):
    response = client.get("/api/cached_queries")
    assert response.status_code == 200
    payload = response.get_json()
    assert "queries" in payload


def test_query_route(client):
    response = client.post("/api/query?confirmed=true")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["issue_count"] == 1


def test_query_route_requires_confirmation(client):
    response = client.post("/api/query")
    assert response.status_code == 400


def test_kanban_route_returns_columns(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/kanban")
    assert response.status_code == 200
    payload = response.get_json()
    assert "columns" in payload
    assert "metrics" in payload
    assert "jql_preview" in payload
    assert "summary_window" in payload
    assert "manager_summary_cards" in payload
    assert "manager_summary_text" in payload
    assert "period_focus" in payload


def test_gantt_route_mode_validation(client):
    response = client.get("/api/gantt?mode=invalid")
    assert response.status_code == 400


def test_export_csv(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/export/csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("Content-Type", "")


def test_query_and_build_separated(client, fake_jira):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    kanban = client.get("/api/kanban")
    assert kanban.status_code == 200
    gantt = client.get("/api/gantt")
    assert gantt.status_code == 200
    assert fake_jira.query_calls == 1


def test_kanban_supports_custom_window(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/kanban?window=weekly&start=2026-02-01T00:00:00Z&end=2026-02-28T00:00:00Z")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["summary_window"]["mode"] == "custom"
