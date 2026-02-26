from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class JiraClientError(Exception):
    pass


@dataclass
class JiraConfig:
    base_url: str
    username: str
    password: str
    verify_ssl: bool = True
    timeout_seconds: int = 30
    jql_filters: list[str] | None = None


class JiraClient:
    def __init__(self, config: JiraConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.auth = (config.username, config.password)
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.config.base_url}{endpoint}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                timeout=self.config.timeout_seconds,
                verify=self.config.verify_ssl,
            )
        except requests.RequestException as error:
            raise JiraClientError(f"Failed to call Jira API: {error}") from error

        if response.status_code in (401, 403):
            raise JiraClientError("Authentication or permission denied by Jira API")
        if response.status_code == 429:
            raise JiraClientError("Jira API rate limit reached")
        if response.status_code >= 500:
            raise JiraClientError("Jira API server error")
        if response.status_code >= 400:
            raise JiraClientError(f"Jira API request failed: {response.status_code} {response.text}")

        return response.json()

    def build_search_jql(self, jql: str | None = None) -> str:
        clauses: list[str] = []
        if self.config.jql_filters:
            clauses.extend(f"({part})" for part in self.config.jql_filters)
        if jql:
            clauses.append(f"({jql})")
        if not clauses:
            raise JiraClientError("At least one JQL clause is required")
        return " AND ".join(clauses)

    def get_issues_by_jql(self, jql: str | None = None) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        start_at = 0
        max_results = 50
        search_jql = self.build_search_jql(jql=jql)
        while True:
            params: dict[str, Any] = {
                "startAt": start_at,
                "maxResults": max_results,
                "expand": "changelog",
                "jql": search_jql,
                "fields": "summary,status,priority,assignee,created,updated,resolutiondate,description,issuetype,sprint",
            }

            data = self._request("GET", "/rest/api/2/search", params=params)
            chunk = data.get("issues", [])
            issues.extend(chunk)

            total = int(data.get("total", len(issues)))
            if start_at + max_results >= total or not chunk:
                break
            start_at += max_results

        return issues
