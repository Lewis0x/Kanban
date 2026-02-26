def test_cached_queries_route(client):
    response = client.get("/api/cached_queries")
    assert response.status_code == 200
    payload = response.get_json()
    assert "queries" in payload


def test_cache_sources_route(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/cache_sources")
    assert response.status_code == 200
    payload = response.get_json()
    assert "sources" in payload


def test_team_issue_history_route(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/history/team_issues")
    assert response.status_code == 200
    payload = response.get_json()
    assert "queries" in payload
    assert payload["query_count"] >= 1


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
    assert "manager_summary_cards" in payload
    assert "period_focus" in payload


def test_kanban_route_returns_assignment_debug_when_enabled(client):
    warm = client.post("/api/query?confirmed=true")
    assert warm.status_code == 200
    response = client.get("/api/kanban?debug_assignment=true")
    assert response.status_code == 200
    payload = response.get_json()
    assert "assignment_debug" in payload
    assert "window" in payload["assignment_debug"]
    assert "rows" in payload["assignment_debug"]


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
