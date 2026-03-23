from pathlib import Path

import pytest

from app.config import load_config, normalize_task_owner_field_id


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


def test_load_config_parses_teams(tmp_path: Path):
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: alice
password: secret
teams:
  - id: algo
    name: 算法组
    owner: 陈兴
    members:
      - 谢屹
      - 张锐岩
      - 陈兴
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(file))
    assert len(cfg["teams"]) == 1
    assert cfg["teams"][0]["id"] == "algo"
    assert cfg["teams"][0]["owner"] == "陈兴"
    assert "谢屹" in cfg["teams"][0]["members"]


def test_load_config_auto_derives_developer_roles_from_teams(tmp_path: Path):
    """When developer_roles is empty, members minus PM/DM/QA are used."""
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: alice
password: secret
role_settings:
  product_manager_roles:
    - 产品A
  dev_manager_roles:
    - 陈兴
  quality_roles:
    - 测试A
teams:
  - id: algo
    name: 算法组
    owner: 陈兴
    members:
      - 谢屹
      - 张锐岩
      - 陈兴
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(file))
    dev_roles = cfg["role_settings"]["developer_roles"]
    assert "谢屹" in dev_roles
    assert "张锐岩" in dev_roles
    # DM (陈兴) should be excluded from auto-derived developer_roles
    assert "陈兴" not in dev_roles


def test_load_config_explicit_developer_roles_not_overridden(tmp_path: Path):
    """When developer_roles is explicitly set, teams.members should not overwrite it."""
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: alice
password: secret
role_settings:
  developer_roles:
    - 开发X
teams:
  - id: algo
    name: 算法组
    owner: 陈兴
    members:
      - 谢屹
      - 张锐岩
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(file))
    assert cfg["role_settings"]["developer_roles"] == ["开发X"]


def test_normalize_task_owner_field_id_numeric_and_explicit():
    assert normalize_task_owner_field_id("12345") == "customfield_12345"
    assert normalize_task_owner_field_id("customfield_12345") == "customfield_12345"


def test_normalize_task_owner_field_id_empty_and_auto():
    assert normalize_task_owner_field_id(None) is None
    assert normalize_task_owner_field_id("") is None
    assert normalize_task_owner_field_id("auto") is None


def test_load_config_normalizes_task_owner_field(tmp_path: Path):
    file = tmp_path / "jira_auth.yaml"
    file.write_text(
        """
base_url: https://jira.example.com/
username: u
password: p
task_owner_field: "12345"
jql_filters:
  - project = X
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(str(file))
    assert cfg["task_owner_field"] == "customfield_12345"
