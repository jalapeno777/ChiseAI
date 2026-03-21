---
project: ChiseAI
scope: infra
type: decision
story_id: ST-INFRA-BOOT-001
date: 2026-02-07
---

Decisions:
- Use Terraform (docker provider) to define the chiseai network and core services (redis/postgres/influxdb/qdrant/grafana) plus dev tooling (gitea/woodpecker/taiga).
- Taiga stack includes RabbitMQ for events/async processing.
- Repo is the canonical source of truth; Taiga two-way sync uses strict conflict rules and creates PRs for repo-canonical changes.
- Redis DB index standardized to 0 across repo configs.
- Ports aligned to AGENTS.md conventions for core ChiseAI services; additional ports selected to avoid conflicts.
- chiseai network uses subnet 172.27.0.0/16 to avoid overlap with existing gridai network on 172.25.0.0/16.
- Woodpecker remapped to host port 8012 to avoid conflict with legacy dashboard on 8002.

Acceptance Criteria:
- AC1: Terraform stack exists under `infrastructure/terraform/` with Docker provider and chiseai network definition.
- AC2: Core services defined (redis/postgres/influxdb/qdrant/grafana) with required ports and labels.
- AC3: Dev tooling defined (gitea/woodpecker/taiga) with ports and labels.
- AC4: `opencode.json` uses Redis DB 0 and Qdrant port 6334.
- AC5: `AGENTS.md` and `.opencode/agent/Aria.md` updated with infra + temp memory guidance.

Notes:
- Temporary memory logging stored in docs/tempmemories until Redis/Qdrant access is restored.
