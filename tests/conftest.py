from __future__ import annotations

from typing import Any

import pytest

from app.main import create_app


class FakeJiraClient:
    def __init__(self):
        self.last_jql = None
        self.query_calls = 0

    def get_issues_by_jql(self, jql=None):
        self.last_jql = jql
        self.query_calls += 1
        issue: dict[str, Any] = {
            "key": "ABC-1",
            "fields": {
                "summary": "Fix bug",
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "issuetype": {"name": "Bug"},
                "assignee": {"displayName": "Alice"},
                "created": "2026-02-01T08:00:00.000+00:00",
                "description": "example",
                "sprint": {"name": "Sprint 11"},
            },
            "changelog": {
                "histories": [
                    {
                        "created": "2026-02-02T08:00:00.000+00:00",
                        "items": [{"field": "assignee", "toString": "Alice"}],
                    },
                    {
                        "created": "2026-02-03T08:00:00.000+00:00",
                        "items": [{"field": "status", "toString": "In Progress"}],
                    },
                    {
                        "created": "2026-02-04T08:00:00.000+00:00",
                        "items": [{"field": "status", "toString": "Done"}],
                    },
                ]
            },
        }
        return [issue]

    def build_search_jql(self, jql=None):
        if jql:
            return f"(project = TEST) AND ({jql})"
        return "(project = TEST)"


@pytest.fixture
def fake_jira():
    return FakeJiraClient()


@pytest.fixture
def app(fake_jira):
    app = create_app(jira_client=fake_jira)
    return app


@pytest.fixture
def client(app):
    return app.test_client()
