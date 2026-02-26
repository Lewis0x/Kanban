from pathlib import Path

import pytest

from app.config import load_config


def test_load_config_reads_password_and_jql_filters(tmp_path: Path):
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: alice
password: secret
verify_ssl: false
request_timeout_seconds: 15
status_mapping:
    todo:
        - Open
        - 已分配
    in_progress:
        - In Progress
        - 开发中
    review:
        - 审核中
        - In Review
    done:
        - Done
        - 已关闭
role_settings:
    product_manager_roles:
        - humeng
        - 胡梦
    dev_manager_roles:
        - hushengquan
        - 胡圣泉
    developer_roles:
        - xieyi
        - 谢屹
    quality_roles:
        - humeng
        - 胡梦
teams:
    - id: platform
      name: 平台组
      owner: hushengquan
      members:
          - chenxing
          - daijianlong
    - id: feature
      name: 功能组
      owner: humeng
      members:
          - xieyi
          - zhangjianfeng
filter_settings:
    allowed_filter_ids:
        - 1001
        - 1002
    default_filter_id: 1002
jql_filters:
  - project = CAD
  - status not in (Closed)
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(file))
    assert cfg["username"] == "alice"
    assert cfg["password"] == "secret"
    assert cfg["verify_ssl"] is False
    assert cfg["request_timeout_seconds"] == 15
    assert cfg["status_mapping"]["todo"] == ["Open", "已分配"]
    assert cfg["status_mapping"]["in_progress"] == ["In Progress", "开发中"]
    assert cfg["status_mapping"]["review"] == ["审核中", "In Review"]
    assert cfg["status_mapping"]["done"] == ["Done", "已关闭"]
    assert cfg["role_settings"]["product_manager_roles"] == ["humeng", "胡梦"]
    assert cfg["role_settings"]["dev_manager_roles"] == ["hushengquan", "胡圣泉"]
    assert cfg["role_settings"]["developer_roles"] == ["xieyi", "谢屹"]
    assert cfg["role_settings"]["quality_roles"] == ["humeng", "胡梦"]
    assert cfg["teams"][0]["id"] == "platform"
    assert cfg["teams"][0]["owner"] == "hushengquan"
    assert cfg["teams"][0]["members"] == ["chenxing", "daijianlong"]
    assert cfg["teams"][1]["name"] == "功能组"
    assert cfg["filter_settings"]["allowed_filter_ids"] == ["1001", "1002"]
    assert cfg["filter_settings"]["default_filter_id"] == "1002"
    assert cfg["jql_filters"] == ["project = CAD", "status not in (Closed)"]


def test_load_config_requires_password(tmp_path: Path):
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: alice
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(str(file))
