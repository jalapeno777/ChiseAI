"""Tests for ci_base_tag_drift_detector."""

from __future__ import annotations


class TestFindLatestCiToolsTag:
    def test_finds_latest_tag(self, tmp_path, monkeypatch):
        import scripts.ci.ci_base_tag_drift_detector as mod

        monkeypatch.setattr(mod, "WOODPECKER_DIR", tmp_path)
        (tmp_path / "ci.yaml").write_text(
            "image: chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        assert mod.find_latest_ci_tools_tag() == "chiseai-ci-tools:py311-20260423"

    def test_picks_newest_when_multiple(self, tmp_path, monkeypatch):
        import scripts.ci.ci_base_tag_drift_detector as mod

        monkeypatch.setattr(mod, "WOODPECKER_DIR", tmp_path)
        (tmp_path / "a.yaml").write_text(
            "image: chiseai-ci-tools:py311-20260301\n", encoding="utf-8"
        )
        (tmp_path / "b.yaml").write_text(
            "image: chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        assert mod.find_latest_ci_tools_tag() == "chiseai-ci-tools:py311-20260423"

    def test_returns_none_when_no_tags(self, tmp_path, monkeypatch):
        import scripts.ci.ci_base_tag_drift_detector as mod

        monkeypatch.setattr(mod, "WOODPECKER_DIR", tmp_path)
        (tmp_path / "ci.yaml").write_text("image: other:tag\n", encoding="utf-8")
        assert mod.find_latest_ci_tools_tag() is None


class TestFindStaleDockerfiles:
    def test_no_stale_when_all_current(self, tmp_path, monkeypatch):
        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        stale = mod.find_stale_dockerfiles("chiseai-ci-tools:py311-20260423")
        assert stale == []

    def test_detects_stale_file(self, tmp_path, monkeypatch):
        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260301\n", encoding="utf-8"
        )
        stale = mod.find_stale_dockerfiles("chiseai-ci-tools:py311-20260423")
        assert len(stale) == 1
        assert stale[0]["file"] == "infrastructure/docker/Dockerfile.ci-tools"
        assert stale[0]["from_date"] == "20260301"
        assert stale[0]["latest_date"] == "20260423"
