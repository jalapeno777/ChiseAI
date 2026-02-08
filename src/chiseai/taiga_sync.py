from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import requests
import yaml


class TaigaSyncError(RuntimeError):
    pass


RepoStatus = Literal["planned", "in_progress", "completed", "blocked", "deprecated"]


@dataclass(frozen=True)
class RepoSprint:
    id: str
    name: str
    status: RepoStatus


@dataclass(frozen=True)
class RepoStory:
    id: str
    title: str
    epic_id: str | None
    sprint_id: str | None
    status: RepoStatus
    acceptance_criteria: list[str]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TaigaSyncError(f"Missing required file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:  # pragma: no cover
        raise TaigaSyncError(f"YAML parse error in {path}: {e}") from e


def load_repo_sprints(workflow_status_path: Path) -> list[RepoSprint]:
    data = _load_yaml(workflow_status_path)
    raw = data.get("sprints", [])
    if not isinstance(raw, list):
        raise TaigaSyncError(f"{workflow_status_path}: sprints must be a list")

    sprints: list[RepoSprint] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "")).strip()
        name = str(s.get("name", "")).strip()
        status = str(s.get("status", "")).strip()
        if (
            not sid
            or not name
            or status
            not in {
                "planned",
                "in_progress",
                "completed",
                "blocked",
                "deprecated",
            }
        ):
            continue
        sprints.append(RepoSprint(id=sid, name=name, status=status))  # type: ignore[arg-type]
    return sprints


def _story_ac_from_validation_registry(
    validation_registry_path: Path,
) -> dict[str, list[str]]:
    data = _load_yaml(validation_registry_path)
    raw = data.get("validations", [])
    if not isinstance(raw, list):
        raise TaigaSyncError(f"{validation_registry_path}: validations must be a list")

    by_story: dict[str, list[str]] = {}
    for v in raw:
        if not isinstance(v, dict):
            continue
        story_id = v.get("story_id")
        ac = v.get("acceptance_criteria")
        if not isinstance(story_id, str) or not story_id.strip():
            continue
        if not isinstance(ac, list) or not all(isinstance(x, str) for x in ac):
            continue
        # Preserve order for human readability.
        by_story[story_id] = [x.strip() for x in ac if x.strip()]
    return by_story


def load_repo_stories(
    *,
    workflow_status_path: Path,
    validation_registry_path: Path,
    include_deprecated: bool = False,
) -> list[RepoStory]:
    wf = _load_yaml(workflow_status_path)
    raw = wf.get("stories", [])
    if not isinstance(raw, list):
        raise TaigaSyncError(f"{workflow_status_path}: stories must be a list")

    ac_by_story = _story_ac_from_validation_registry(validation_registry_path)

    stories: list[RepoStory] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "")).strip()
        title = str(s.get("title", "")).strip()
        epic_id = s.get("epic_id")
        sprint_id = s.get("sprint_id")
        status = str(s.get("status", "")).strip()

        if not sid or not title:
            continue
        if status not in {
            "planned",
            "in_progress",
            "completed",
            "blocked",
            "deprecated",
        }:
            continue
        if status == "deprecated" and not include_deprecated:
            continue

        stories.append(
            RepoStory(
                id=sid,
                title=title,
                epic_id=str(epic_id).strip() if isinstance(epic_id, str) else None,
                sprint_id=(
                    str(sprint_id).strip() if isinstance(sprint_id, str) else None
                ),
                status=status,  # type: ignore[arg-type]
                acceptance_criteria=ac_by_story.get(sid, []),
            )
        )
    return stories


def canonical_story_checksum(story: RepoStory) -> str:
    payload = {
        "id": story.id,
        "title": story.title,
        "epic_id": story.epic_id,
        "sprint_id": story.sprint_id,
        "status": story.status,
        "acceptance_criteria": story.acceptance_criteria,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _norm_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise TaigaSyncError("TAIGA_BASE_URL is empty")
    return base_url


def _auth_header(token: str) -> str:
    token = token.strip()
    if not token:
        raise TaigaSyncError("TAIGA_TOKEN is empty")
    if token.lower().startswith("bearer "):
        return token
    if token.lower().startswith("application "):
        # Older Taiga setups accept Application tokens.
        return token
    return f"Bearer {token}"


@dataclass
class TaigaConfig:
    base_url: str
    project_slug: str
    token: str | None = None
    username: str | None = None
    password: str | None = None
    timeout_s: float = 20.0
    milestone_start: str | None = None
    milestone_finish: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> TaigaConfig:
        env = dict(os.environ) if env is None else env
        base_url = _norm_base_url(
            env.get("TAIGA_BASE_URL", "http://host.docker.internal:9002")
        )
        project_slug = env.get("TAIGA_PROJECT_SLUG", "").strip()
        token = env.get("TAIGA_TOKEN")
        username = env.get("TAIGA_USERNAME")
        password = env.get("TAIGA_PASSWORD")
        timeout_s = float(env.get("TAIGA_TIMEOUT_S", "20").strip() or "20")
        milestone_start = env.get("TAIGA_MILESTONE_START")
        milestone_finish = env.get("TAIGA_MILESTONE_FINISH")
        return cls(
            base_url=base_url,
            project_slug=project_slug,
            token=token.strip() if isinstance(token, str) and token.strip() else None,
            username=(
                username.strip()
                if isinstance(username, str) and username.strip()
                else None
            ),
            password=(
                password.strip()
                if isinstance(password, str) and password.strip()
                else None
            ),
            timeout_s=timeout_s,
            milestone_start=(
                milestone_start.strip()
                if isinstance(milestone_start, str) and milestone_start.strip()
                else None
            ),
            milestone_finish=(
                milestone_finish.strip()
                if isinstance(milestone_finish, str) and milestone_finish.strip()
                else None
            ),
        )

    def validate(self) -> None:
        if not self.project_slug:
            raise TaigaSyncError("Missing required env var: TAIGA_PROJECT_SLUG")
        if not (self.token or (self.username and self.password)):
            raise TaigaSyncError(
                "Missing Taiga auth. Set TAIGA_TOKEN or TAIGA_USERNAME+TAIGA_PASSWORD."
            )


class TaigaClient:
    def __init__(self, cfg: TaigaConfig) -> None:
        self._cfg = cfg
        self._sess = requests.Session()
        self._sess.headers.update({"Content-Type": "application/json"})
        self._token: str | None = None

    @property
    def base_api(self) -> str:
        return f"{self._cfg.base_url}/api/v1"

    def _ensure_auth(self) -> None:
        if self._token:
            return
        if self._cfg.token:
            self._token = self._cfg.token
            self._sess.headers["Authorization"] = _auth_header(self._token)
            return
        if not (self._cfg.username and self._cfg.password):
            raise TaigaSyncError("No Taiga auth configured")
        url = f"{self.base_api}/auth"
        payload = {
            "type": "normal",
            "username": self._cfg.username,
            "password": self._cfg.password,
        }
        r = self._sess.post(url, json=payload, timeout=self._cfg.timeout_s)
        if r.status_code >= 400:
            raise TaigaSyncError(f"Taiga auth failed ({r.status_code}): {r.text[:200]}")
        data = r.json()
        tok = data.get("auth_token")
        if not isinstance(tok, str) or not tok.strip():
            raise TaigaSyncError("Taiga auth response missing auth_token")
        self._token = tok.strip()
        self._sess.headers["Authorization"] = _auth_header(self._token)

    def get_project(self) -> dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_api}/projects/by_slug"
        r = self._sess.get(
            url, params={"slug": self._cfg.project_slug}, timeout=self._cfg.timeout_s
        )
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to fetch Taiga project slug={self._cfg.project_slug!r} "
                f"({r.status_code}): {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, dict) or "id" not in data:
            raise TaigaSyncError("Unexpected Taiga project response")
        return data

    def list_userstory_statuses(self, *, project_id: int) -> list[dict[str, Any]]:
        self._ensure_auth()
        url = f"{self.base_api}/userstory-statuses"
        r = self._sess.get(
            url, params={"project": project_id}, timeout=self._cfg.timeout_s
        )
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to list userstory statuses: {r.status_code} {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, list):
            raise TaigaSyncError("Unexpected userstory-statuses response")
        return [x for x in data if isinstance(x, dict)]

    def list_milestones(self, *, project_id: int) -> list[dict[str, Any]]:
        self._ensure_auth()
        url = f"{self.base_api}/milestones"
        r = self._sess.get(
            url, params={"project": project_id}, timeout=self._cfg.timeout_s
        )
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to list milestones: {r.status_code} {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, list):
            raise TaigaSyncError("Unexpected milestones response")
        return [x for x in data if isinstance(x, dict)]

    def create_milestone(
        self, *, project_id: int, name: str, start: str, finish: str
    ) -> dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_api}/milestones"
        payload = {
            "project": project_id,
            "name": name,
            "estimated_start": start,
            "estimated_finish": finish,
        }
        r = self._sess.post(url, json=payload, timeout=self._cfg.timeout_s)
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to create milestone {name!r}: {r.status_code} {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, dict):
            raise TaigaSyncError("Unexpected milestone create response")
        return data

    def search(self, *, project_id: int, text: str) -> dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_api}/search"
        params: dict[str, str | int] = {"project": project_id, "text": text}
        r = self._sess.get(
            url,
            params=params,
            timeout=self._cfg.timeout_s,
        )
        if r.status_code >= 400:
            raise TaigaSyncError(f"Failed to search: {r.status_code} {r.text[:200]}")
        data = r.json()
        if not isinstance(data, dict):
            raise TaigaSyncError("Unexpected search response")
        return data

    def create_userstory(
        self,
        *,
        project_id: int,
        subject: str,
        description: str,
        milestone_id: int | None,
        status_id: int,
        tags: list[str],
    ) -> dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_api}/userstories"
        payload: dict[str, Any] = {
            "project": project_id,
            "subject": subject,
            "description": description,
            "status": status_id,
            "tags": tags,
        }
        if milestone_id is not None:
            payload["milestone"] = milestone_id
        r = self._sess.post(url, json=payload, timeout=self._cfg.timeout_s)
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to create user story {subject!r}: "
                f"{r.status_code} {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, dict):
            raise TaigaSyncError("Unexpected userstory create response")
        return data

    def update_userstory(
        self, *, userstory_id: int, patch: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_api}/userstories/{userstory_id}"
        r = self._sess.patch(url, json=patch, timeout=self._cfg.timeout_s)
        if r.status_code >= 400:
            raise TaigaSyncError(
                f"Failed to update userstory id={userstory_id}: "
                f"{r.status_code} {r.text[:200]}"
            )
        data = r.json()
        if not isinstance(data, dict):
            raise TaigaSyncError("Unexpected userstory update response")
        return data


def repo_status_to_taiga_userstory_status_name(status: RepoStatus) -> str:
    # Keep this conservative: we resolve actual ids by best-effort name matching.
    return {
        "planned": "New",
        "in_progress": "In progress",
        "blocked": "Blocked",
        "completed": "Done",
        "deprecated": "Archived",
    }[status]


def resolve_taiga_status_id(
    statuses: list[dict[str, Any]], desired_name: str
) -> int | None:
    desired = desired_name.strip().lower()
    for s in statuses:
        name = str(s.get("name", "")).strip().lower()
        if name == desired:
            sid = s.get("id")
            if isinstance(sid, int):
                return sid
    # Fallback: contains match for common variations.
    for s in statuses:
        name = str(s.get("name", "")).strip().lower()
        if desired in name:
            sid = s.get("id")
            if isinstance(sid, int):
                return sid
    return None


@dataclass
class SyncStateStory:
    taiga_userstory_id: int
    taiga_ref: int | None
    last_repo_checksum: str
    last_taiga_checksum: str | None = None


@dataclass
class SyncState:
    project_slug: str
    project_id: int
    stories: dict[str, SyncStateStory]


def load_sync_state(path: Path) -> SyncState | None:
    if not path.exists():
        return None
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return None
    project_slug = data.get("project_slug")
    project_id = data.get("project_id")
    raw_stories = data.get("stories", {})
    if not isinstance(project_slug, str) or not isinstance(project_id, int):
        return None
    if not isinstance(raw_stories, dict):
        raw_stories = {}
    stories: dict[str, SyncStateStory] = {}
    for k, v in raw_stories.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        tid = v.get("taiga_userstory_id")
        if not isinstance(tid, int):
            continue
        tref = v.get("taiga_ref")
        last_repo = v.get("last_repo_checksum")
        last_taiga = v.get("last_taiga_checksum")
        if not isinstance(last_repo, str):
            continue
        stories[k] = SyncStateStory(
            taiga_userstory_id=tid,
            taiga_ref=tref if isinstance(tref, int) else None,
            last_repo_checksum=last_repo,
            last_taiga_checksum=last_taiga if isinstance(last_taiga, str) else None,
        )
    return SyncState(project_slug=project_slug, project_id=project_id, stories=stories)


def save_sync_state(path: Path, state: SyncState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {
        "project_slug": state.project_slug,
        "project_id": state.project_id,
        "stories": {
            sid: {
                "taiga_userstory_id": s.taiga_userstory_id,
                "taiga_ref": s.taiga_ref,
                "last_repo_checksum": s.last_repo_checksum,
                "last_taiga_checksum": s.last_taiga_checksum,
            }
            for sid, s in sorted(state.stories.items())
        },
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def format_taiga_description(*, story: RepoStory) -> str:
    lines = [
        f"Repo Story ID: {story.id}",
        f"Epic: {story.epic_id or '-'}",
        f"Sprint: {story.sprint_id or '-'}",
        f"Repo Status: {story.status}",
        "",
        "Acceptance Criteria:",
    ]
    if story.acceptance_criteria:
        for ac in story.acceptance_criteria:
            lines.append(f"- {ac}")
    else:
        lines.append("- (none found in docs/validation/validation-registry.yaml)")
    return "\n".join(lines).strip() + "\n"


@dataclass(frozen=True)
class PlannedAction:
    kind: Literal[
        "create_milestone", "create_userstory", "update_userstory", "conflict"
    ]
    story_id: str | None
    detail: str


def plan_and_sync_repo_to_taiga(
    *,
    cfg: TaigaConfig,
    workflow_status_path: Path,
    validation_registry_path: Path,
    state_path: Path,
    apply: bool,
    force: bool,
    include_deprecated: bool,
) -> list[PlannedAction]:
    cfg.validate()
    client = TaigaClient(cfg)
    project = client.get_project()
    project_id = int(project["id"])

    existing_state = load_sync_state(state_path)
    if existing_state is None:
        state = SyncState(
            project_slug=cfg.project_slug, project_id=project_id, stories={}
        )
    else:
        if (
            existing_state.project_slug != cfg.project_slug
            or existing_state.project_id != project_id
        ):
            raise TaigaSyncError(
                f"Sync state mismatch: {state_path} references "
                f"{existing_state.project_slug}/{existing_state.project_id} "
                f"but Taiga project is {cfg.project_slug}/{project_id}"
            )
        state = existing_state

    # Milestones keyed by sprint_id -> taiga milestone id
    milestones = client.list_milestones(project_id=project_id)
    milestone_by_name: dict[str, int] = {}
    for m in milestones:
        mid = m.get("id")
        name = str(m.get("name", "")).strip()
        if isinstance(mid, int) and name:
            milestone_by_name[name] = mid

    sprints = load_repo_sprints(workflow_status_path)
    sprint_name_by_id = {
        s.id: s.name for s in sprints if include_deprecated or s.status != "deprecated"
    }

    actions: list[PlannedAction] = []
    milestone_id_by_sprint_id: dict[str, int] = {}
    start = cfg.milestone_start or date.today().isoformat()
    finish = cfg.milestone_finish or (date.today() + timedelta(days=90)).isoformat()
    for sid, name in sorted(sprint_name_by_id.items()):
        mid = milestone_by_name.get(name)
        if mid is None:
            actions.append(
                PlannedAction(
                    kind="create_milestone", story_id=None, detail=f"{sid}: {name}"
                )
            )
            if apply:
                created = client.create_milestone(
                    project_id=project_id, name=name, start=start, finish=finish
                )
                mid_val = created.get("id")
                if not isinstance(mid_val, int):
                    raise TaigaSyncError("Taiga milestone create missing id")
                mid = mid_val
        if mid is not None:
            milestone_id_by_sprint_id[sid] = mid

    statuses = client.list_userstory_statuses(project_id=project_id)

    stories = load_repo_stories(
        workflow_status_path=workflow_status_path,
        validation_registry_path=validation_registry_path,
        include_deprecated=include_deprecated,
    )

    for st in sorted(stories, key=lambda x: x.id):
        desired_status_name = repo_status_to_taiga_userstory_status_name(st.status)
        desired_status_id = resolve_taiga_status_id(statuses, desired_status_name)
        if desired_status_id is None:
            raise TaigaSyncError(
                f"Could not resolve Taiga userstory status id for "
                f"{desired_status_name!r}. "
                "Create a matching status in Taiga or adjust mapping."
            )

        subject = f"{st.id} {st.title}"
        description = format_taiga_description(story=st)
        milestone_id = (
            milestone_id_by_sprint_id.get(st.sprint_id or "") if st.sprint_id else None
        )
        tags = [st.epic_id] if st.epic_id else []

        repo_checksum = canonical_story_checksum(st)
        state_entry = state.stories.get(st.id)
        if state_entry is None:
            # Bootstrap: attempt to find an existing story by search; otherwise create.
            found_userstory_id: int | None = None
            found_ref: int | None = None
            try:
                sr = client.search(project_id=project_id, text=st.id)
                # Search result shape varies; prefer userstories list with exact
                # subject prefix match.
                cands = sr.get("userstories") if isinstance(sr, dict) else None
                if isinstance(cands, list):
                    for c in cands:
                        if not isinstance(c, dict):
                            continue
                        subj = str(c.get("subject", "")).strip()
                        if subj.startswith(f"{st.id} "):
                            uid = c.get("id")
                            if isinstance(uid, int):
                                found_userstory_id = uid
                                found_ref = (
                                    c.get("ref")
                                    if isinstance(c.get("ref"), int)
                                    else None
                                )
                                break
            except TaigaSyncError:
                # Search is best-effort for bootstrap; do not block if unavailable.
                pass

            if found_userstory_id is not None:
                state.stories[st.id] = SyncStateStory(
                    taiga_userstory_id=found_userstory_id,
                    taiga_ref=found_ref,
                    last_repo_checksum=repo_checksum,
                    last_taiga_checksum=None,
                )
                actions.append(
                    PlannedAction(
                        kind="update_userstory",
                        story_id=st.id,
                        detail=(
                            "adopt existing taiga_userstory_id=" f"{found_userstory_id}"
                        ),
                    )
                )
            else:
                actions.append(
                    PlannedAction(
                        kind="create_userstory", story_id=st.id, detail=subject
                    )
                )
                if apply:
                    created = client.create_userstory(
                        project_id=project_id,
                        subject=subject,
                        description=description,
                        milestone_id=milestone_id,
                        status_id=desired_status_id,
                        tags=tags,
                    )
                    uid = created.get("id")
                    if not isinstance(uid, int):
                        raise TaigaSyncError("Taiga userstory create missing id")
                    uref = (
                        created.get("ref")
                        if isinstance(created.get("ref"), int)
                        else None
                    )
                    state.stories[st.id] = SyncStateStory(
                        taiga_userstory_id=uid,
                        taiga_ref=uref,
                        last_repo_checksum=repo_checksum,
                        last_taiga_checksum=_taiga_userstory_checksum(created),
                    )
            continue

        # Existing: if repo changed since last run, update Taiga canonical fields.
        if state_entry.last_repo_checksum == repo_checksum:
            continue

        # Before patching, detect whether Taiga's canonical fields were edited
        # since last sync.
        # We only have checksums, so this is best-effort: if we previously
        # stored a taiga checksum
        # and it changed, treat as conflict unless --force.
        if state_entry.last_taiga_checksum and not force:
            actions.append(
                PlannedAction(
                    kind="conflict",
                    story_id=st.id,
                    detail=(
                        "Taiga canonical fields changed since last sync; "
                        "rerun with --force to overwrite."
                    ),
                )
            )
            continue

        patch: dict[str, Any] = {
            "subject": subject,
            "description": description,
            "status": desired_status_id,
            "tags": tags,
        }
        patch["milestone"] = milestone_id
        actions.append(
            PlannedAction(
                kind="update_userstory",
                story_id=st.id,
                detail=f"id={state_entry.taiga_userstory_id}",
            )
        )
        if apply:
            updated = client.update_userstory(
                userstory_id=state_entry.taiga_userstory_id, patch=patch
            )
            taiga_ck = _taiga_userstory_checksum(updated)
            state.stories[st.id] = SyncStateStory(
                taiga_userstory_id=state_entry.taiga_userstory_id,
                taiga_ref=state_entry.taiga_ref,
                last_repo_checksum=repo_checksum,
                last_taiga_checksum=taiga_ck,
            )
        else:
            state.stories[st.id] = SyncStateStory(
                taiga_userstory_id=state_entry.taiga_userstory_id,
                taiga_ref=state_entry.taiga_ref,
                last_repo_checksum=repo_checksum,
                last_taiga_checksum=state_entry.last_taiga_checksum,
            )

    if apply:
        save_sync_state(state_path, state)
    return actions


def _taiga_userstory_checksum(userstory: dict[str, Any]) -> str:
    # Canonical fields, per docs/taiga-sync.md (repo canonical).
    payload = {
        "subject": userstory.get("subject"),
        "description": userstory.get("description"),
        "status": userstory.get("status"),
        "milestone": userstory.get("milestone"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
