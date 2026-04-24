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

    def test_detects_stale_in_multi_stage_with_valid_first_stage(
        self, tmp_path, monkeypatch
    ):
        """Multi-stage Dockerfile where stage 1 is current and stage 2 IS stale."""
        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        # Stage 1: current chiseai-ci-tools, Stage 2: stale chiseai-ci-tools
        # Both lines match the regex fully (no "AS builder" suffix)
        (docker_dir / "Dockerfile.ci-autocog").write_text(
            "FROM chiseai-ci-tools:py311-20260423\nFROM chiseai-ci-tools:py311-20260301\n",
            encoding="utf-8",
        )
        stale = mod.find_stale_dockerfiles("chiseai-ci-tools:py311-20260423")
        assert len(stale) == 1
        assert stale[0]["file"] == "infrastructure/docker/Dockerfile.ci-autocog"
        assert stale[0]["from_date"] == "20260301"
        assert stale[0]["latest_date"] == "20260423"

    def test_detects_multiple_stale_in_same_file(self, tmp_path, monkeypatch):
        """Multiple FROM chiseai-ci-tools lines in same file, both stale."""
        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260301\n"
            "FROM chiseai-ci-tools:py311-20260215\n",
            encoding="utf-8",
        )
        stale = mod.find_stale_dockerfiles("chiseai-ci-tools:py311-20260423")
        assert len(stale) == 2
        dates = {s["from_date"] for s in stale}
        assert dates == {"20260301", "20260215"}

    def test_detects_stale_with_as_alias(self, tmp_path, monkeypatch):
        """Multi-stage Dockerfile with AS alias suffix should be detected as stale."""
        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260301 AS builder\n", encoding="utf-8"
        )
        stale = mod.find_stale_dockerfiles("chiseai-ci-tools:py311-20260423")
        assert len(stale) == 1
        assert stale[0]["file"] == "infrastructure/docker/Dockerfile.ci-tools"
        assert stale[0]["from_date"] == "20260301"
        assert stale[0]["latest_date"] == "20260423"


class TestMainExitCode:
    def test_main_exit_code_1_on_stale(self, tmp_path, monkeypatch):
        """CLI returns exit code 1 when stale Dockerfiles found."""
        import sys

        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "WOODPECKER_DIR", tmp_path)
        monkeypatch.setattr(sys, "argv", ["ci_base_tag_drift_detector.py"])
        (tmp_path / "ci.yaml").write_text(
            "image: chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260301\n", encoding="utf-8"
        )
        exit_code = mod.main()
        assert exit_code == 1

    def test_main_exit_code_0_when_all_current(self, tmp_path, monkeypatch):
        """CLI returns exit code 0 when all Dockerfiles are current."""
        import sys

        import scripts.ci.ci_base_tag_drift_detector as mod

        docker_dir = tmp_path / "infrastructure" / "docker"
        docker_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "DOCKER_DIR", docker_dir)
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "WOODPECKER_DIR", tmp_path)
        monkeypatch.setattr(sys, "argv", ["ci_base_tag_drift_detector.py"])
        (tmp_path / "ci.yaml").write_text(
            "image: chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        (docker_dir / "Dockerfile.ci-tools").write_text(
            "FROM chiseai-ci-tools:py311-20260423\n", encoding="utf-8"
        )
        exit_code = mod.main()
        assert exit_code == 0
