import pytest

from app.jira_client import JiraClient, JiraClientError, JiraConfig


class FakeResponse:
    def __init__(self, status_code, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.auth = None
        self.headers = {}

    def request(self, **kwargs):
        return self.responses.pop(0)


def test_auth_error_raises():
    session = FakeSession([FakeResponse(401, {})])
    client = JiraClient(JiraConfig("https://jira", "u", "p"), session=session)
    with pytest.raises(JiraClientError):
        client.get_issues_by_jql("project = CAD")


def test_jql_issues_pagination():
    first = FakeResponse(200, {"issues": [{"key": "A-1"}], "total": 60})
    second = FakeResponse(200, {"issues": [{"key": "A-2"}], "total": 60})
    third = FakeResponse(200, {"issues": [], "total": 60})
    session = FakeSession([first, second, third])
    client = JiraClient(JiraConfig("https://jira", "u", "p"), session=session)
    items = client.get_issues_by_jql("project = CAD")
    assert len(items) == 2


def test_build_search_jql_with_configured_filters():
    session = FakeSession([])
    client = JiraClient(
        JiraConfig(
            "https://jira",
            "u",
            "p",
            jql_filters=["project = CAD", "priority in (High, Highest)"],
        ),
        session=session,
    )
    jql = client.build_search_jql("assignee = currentUser()")
    assert "(project = CAD)" in jql
    assert "(priority in (High, Highest))" in jql
    assert "(assignee = currentUser())" in jql


def test_build_search_jql_requires_clause():
    client = JiraClient(JiraConfig("https://jira", "u", "p"), session=FakeSession([]))
    with pytest.raises(JiraClientError):
        client.build_search_jql(None)
