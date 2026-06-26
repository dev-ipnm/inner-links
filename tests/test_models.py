"""Tests for site_relinker.models — enums, Pydantic models, and exceptions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from site_relinker.models import (
    AppConfig,
    BackendError,
    BackendType,
    ConfigError,
    IfLinkedPolicy,
    InputError,
    LinkOperation,
    MatchStrategy,
    Operation,
    ScopeDefinition,
    ScopeType,
    SiteRelinkerError,
    StaticConfig,
    WordPressConfig,
)


class TestLinkOperation:
    """Tests for the LinkOperation model."""

    def test_link_operation_valid_add(self) -> None:
        """All required fields for an add operation are accepted."""
        op = LinkOperation(
            operation=Operation.ADD,
            url="/page.html",
            anchor="click here",
            target_url="/target.html",
        )
        assert op.operation == Operation.ADD
        assert op.url == "/page.html"
        assert op.anchor == "click here"
        assert op.target_url == "/target.html"
        assert op.scope_type == ScopeType.WHOLE_BODY
        assert op.if_linked is None

    def test_link_operation_valid_remove(self) -> None:
        """Remove operation is valid without target_url."""
        op = LinkOperation(
            operation=Operation.REMOVE,
            url="/page.html",
            anchor="click here",
        )
        assert op.operation == Operation.REMOVE
        assert op.target_url is None

    def test_link_operation_missing_target_url_for_add(self) -> None:
        """Add operation without target_url raises a validation error."""
        with pytest.raises(ValidationError, match="target_url"):
            LinkOperation(
                operation=Operation.ADD,
                url="/page.html",
                anchor="click here",
            )

    def test_link_operation_invalid_operation(self) -> None:
        """Unknown operation string raises a validation error."""
        with pytest.raises(ValidationError):
            LinkOperation(
                operation="invalid",  # type: ignore[arg-type]
                url="/page.html",
                anchor="click here",
            )


class TestScopeDefinition:
    """Tests for the ScopeDefinition model."""

    def test_scope_definition_element_id(self) -> None:
        """Valid element_id scope is accepted."""
        scope = ScopeDefinition(
            scope_type=ScopeType.ELEMENT_ID,
            scope_value="main-content",
        )
        assert scope.scope_type == ScopeType.ELEMENT_ID
        assert scope.scope_value == "main-content"

    def test_scope_definition_empty_is_whole_body(self) -> None:
        """Empty scope defaults to WHOLE_BODY."""
        scope = ScopeDefinition()
        assert scope.scope_type == ScopeType.WHOLE_BODY
        assert scope.scope_value is None


class TestAppConfig:
    """Tests for the AppConfig model."""

    def test_app_config_domains_required(self, tmp_path: Path) -> None:
        """AppConfig with empty domains list raises a validation error."""
        with pytest.raises(ValidationError, match="domain"):
            AppConfig(
                backend=BackendType.STATIC,
                domains=[],
                static=StaticConfig(
                    web_root=tmp_path,
                    output_dir=tmp_path / "out",
                ),
            )

    def test_app_config_match_strategy_nth_requires_n(
        self, tmp_path: Path
    ) -> None:
        """NTH match strategy without match_n raises a validation error."""
        with pytest.raises(ValidationError, match="match_n"):
            AppConfig(
                backend=BackendType.STATIC,
                domains=["example.com"],
                match_strategy=MatchStrategy.NTH,
                static=StaticConfig(
                    web_root=tmp_path,
                    output_dir=tmp_path / "out",
                ),
            )


class TestStaticConfig:
    """Tests for the StaticConfig model."""

    def test_static_config_paths_validated(self, tmp_path: Path) -> None:
        """StaticConfig accepts valid paths and stores them as Path objects."""
        config = StaticConfig(
            web_root=tmp_path / "site",
            output_dir=tmp_path / "output",
        )
        assert isinstance(config.web_root, Path)
        assert isinstance(config.output_dir, Path)
        assert config.extensions == ["html", "htm", "shtml"]
        assert config.encoding == "utf-8"


class TestWordPressConfig:
    """Tests for the WordPressConfig model."""

    def test_wordpress_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WordPressConfig can be constructed with values from env vars."""
        monkeypatch.setenv("WP_DB_HOST", "db.example.com")
        monkeypatch.setenv("WP_DB_PORT", "3307")
        monkeypatch.setenv("WP_DB_USER", "admin")
        monkeypatch.setenv("WP_DB_PASSWORD", "secret")
        monkeypatch.setenv("WP_DB_NAME", "wp_prod")

        config = WordPressConfig(
            db_host=os.environ["WP_DB_HOST"],
            db_port=int(os.environ["WP_DB_PORT"]),
            db_user=os.environ["WP_DB_USER"],
            db_password=os.environ["WP_DB_PASSWORD"],
            db_name=os.environ["WP_DB_NAME"],
        )
        assert config.db_host == "db.example.com"
        assert config.db_port == 3307
        assert config.db_user == "admin"
        assert config.db_password == "secret"
        assert config.db_name == "wp_prod"


class TestExceptions:
    """Tests for the custom exception hierarchy."""

    def test_custom_exceptions_hierarchy(self) -> None:
        """All custom exceptions inherit from SiteRelinkerError."""
        assert issubclass(ConfigError, SiteRelinkerError)
        assert issubclass(InputError, SiteRelinkerError)
        assert issubclass(BackendError, SiteRelinkerError)
        assert issubclass(SiteRelinkerError, Exception)

        with pytest.raises(SiteRelinkerError):
            raise ConfigError("bad config")

        with pytest.raises(SiteRelinkerError):
            raise InputError("bad input")

        with pytest.raises(SiteRelinkerError):
            raise BackendError("backend failed")
