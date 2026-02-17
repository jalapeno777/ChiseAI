# AGENTS - Quick Reference for Opencode Swarm

> **Critical**: Load skills and run commands rather than reading full docs.

## 🚀 Quick Start for Agents

### Before Any Work
1. **MEM-SCAN**: Read nearest AGENTS.md for your scope
2. **Load Skill**: Identify task type → Load relevant skill (see "When to Use What" below)
3. **Start Iteration**: `.opencode/command/chise-iterloop-start.md`
4. **Claim Ownership**: `.opencode/command/chise-claim-ownership.md` (if parallel work)

### Standard Workflow
```
skill(name="chiseai-git-workflow")          # Load git workflow skill
→ chise-iterloop-start                      # Start iteration
→ chise-claim-ownership                     # Claim scope (if parallel)
→ [Do work following skill guidance]
→ chise-precommit-gates                     # Validate before PR
→ chise-iterloop-close                      # Close and promote learnings
```

## 🎯 When to Use What Skills (Decision Guide)

### "I'm starting a new story..."
**Load:** `chiseai-git-workflow`
**Then run:** `chise-iterloop-start` command
**Why:** Sets up proper branch isolation and iteration tracking from the start

### "I need to delegate work to multiple agents..." (Jarvis only)
**Load:** `chiseai-worker-contracts` + `chiseai-parallel-safety`
**Then run:** `chise-claim-ownership` command
**Must include:** Complete worker contract in delegation
**Why:** Prevents scope conflicts and ensures safety guards

### "I'm about to edit files..."
**Load:** `chiseai-git-workflow`
**Then run:** `chise-swarm-session` (verify) command
**Why:** Ensures you're in the right branch/worktree with clean state

### "I'm working with Redis or Qdrant..."
**Load:** `chiseai-memory-ops`
**Why:** Provides correct key patterns, TTL settings, and fallback strategies

### "I'm preparing to create a PR..."
**Load:** `chiseai-validation`
**Then run:** `chise-precommit-gates` command
**Why:** Ensures all validation layers pass before handoff

### "CI failed on my PR..."
**Load:** `chiseai-validation`
**Then run:** `chise-ci-root-cause` → `chise-ci-failure-bundle` commands
**Why:** Systematic diagnosis with proper evidence collection

### "There's a merge conflict or incident..."
**Load:** `chiseai-incident-response`
**Then run:** `chise-incident-log` command
**For P0/P1:** Schedule post-mortem with `chise-postmortem-create`
**Why:** Structured logging and learning from failures

### "I need to clean up branches..."
**Load:** `chiseai-branch-hygiene`
**Then run:** `chise-branch-hygiene-check` command
**Why:** Systematic cleanup with Redis tracking

### "I'm creating Docker containers..."
**Load:** `chiseai-docker-governance`
**Why:** Ensures correct network, labels, and protected container awareness

### "I'm doing BMAD workflow tasks..."
**Load:** `chiseai-workflow-commands`
**Then run:** Relevant BMAD command (e.g., `bmad-bmm-create-prd`)
**Why:** Routes you to the correct workflow command for your task

### "I'm writing Python code..."
**Load:** `python-quality`
**Why:** Ensures code passes repo-configured quality checks (black, ruff, pytest)

### "I need to merge in an emergency..."
**Load:** `chiseai-git-workflow` (for context)
**Then run:** `chise-emergency-merge-override` command
**Why:** Documents the bypass procedure with required approvals

## 📋 Quick Skill Reference Table

| Skill | Primary Use | Key Commands |
|-------|-------------|--------------|
| `chiseai-git-workflow` | Git operations, branching, PRs | `chise-swarm-session`, `chise-precommit-gates` |
| `chiseai-memory-ops` | Redis/Qdrant operations | `chise-iterloop-start`, `chise-iterloop-close` |
| `chiseai-parallel-safety` | Parallel work delegation | `chise-claim-ownership`, `chise-check-ownership` |
| `chiseai-validation` | Quality gates, CI diagnosis | `chise-ci-root-cause`, `chise-ci-failure-bundle` |
| `chiseai-worker-contracts` | Jarvis-to-worker delegation | Every delegation must use |
| `chiseai-branch-hygiene` | Branch lifecycle management | `chise-branch-hygiene-check` |
| `chiseai-incident-response` | Incident logging, post-mortems | `chise-incident-log`, `chise-postmortem-create` |
| `chiseai-docker-governance` | Container/network config | N/A |
| `chiseai-workflow-commands` | BMAD planning/implementation | All `bmad-*` commands |
| `python-quality` | Python code quality | N/A |

## 🔧 Skill Loading Pattern

```markdown
When starting work:
1. Identify your task type from "When to Use What" above
2. Load the relevant skill: skill(name="skill-name")
3. Follow the skill's guidance
4. Run associated commands as needed
5. Close with `chise-iterloop-close` when done
```

## 🆘 Emergency Procedures

- **Emergency merge override**: `.opencode/command/chise-emergency-merge-override.md`
- **CI failure diagnosis**: `chise-ci-root-cause.md` → `chise-ci-failure-bundle.md`
- **Incident logging**: `chise-incident-log.md`
- **Post-mortem creation**: `chise-postmortem-create.md`

## 📚 Full Documentation

- **Workflow Status**: `docs/bmm-workflow-status.yaml`
- **Validation Registry**: `docs/validation/validation-registry.yaml`
- **Skills Directory**: `.opencode/skills/`
- **Commands Directory**: `.opencode/command/`
- **Post-Mortems**: `docs/postmortems/`

---

## CRITICAL WORKFLOW SUMMARY

- **Data-first:** finish Phase 0 (Data Gathering) before analysis
- **Granular tasks:** small, clear validation criteria
- **Sequential:** no parallel work until data foundation complete
- **Quality gates:** each task must pass validation

---

## Git Safety Essentials

- Never work on `main` without explicit human approval
- Run `git status -sb` before/after operations
- Only `merlin` may open/update/close PRs
- Use `feature/<story-id>-<slug>` branches
- PR titles must contain a recognized story id token:
  - `ST-*`, `CH-*`, `FT-*`, `REWARD-*`, `REPO-*`, `SAFETY-*`, `BRANCH-*`, `PAPER-*`, `RECON-*` (must include a digit)
- Before switching branches, working tree must be clean

---

## Docker & Container Connectivity (CRITICAL)

⚠️ **⚠️⚠️ CRITICAL REMINDER - READ THIS FIRST ⚠️⚠️⚠️**

**WHEN TESTING DOCKER CONTAINERS FROM THIS ENVIRONMENT:**

1. **If you are in a Docker container** (like this agent environment):
   - Use `curl http://host.docker.internal:8502` to test dashboard
   - DO NOT use `localhost` - it refers to your container, not the host

2. **If you are on the host machine** (laptop/desktop):
   - Use `curl http://localhost:8502` to test dashboard

3. **When container needs to reach other services:**
   - Use `host.docker.internal` for PostgreSQL, Redis, etc. when connecting to host services
   - Example: `postgresql://user:pass@host.docker.internal:5434/db`

**THIS IS NOT OPTIONAL. VIOLATIONS WILL CAUSE FAILURES.**

---

### Docker Connectivity Guidance

**Inter-container communication (chiseai network):**
- Containers on the `chiseai` network communicate using service names: `chiseai-redis`, `chiseai-postgres`, `chiseai-qdrant`, etc.
- Use `host.docker.internal` only when a container must reach services running on the host machine.

**Why This Matters**
- Docker containers run in an isolated network namespace
- `localhost` inside a container refers to the container itself, not the host machine
- Using `localhost` will fail to connect to host services (PostgreSQL, Redis, etc.)

**Correct Usage Examples**
```yaml
# Inter-container on chiseai network (preferred for container-to-container)
database:
  host: "chiseai-postgres"  # Service name on chiseai network
  port: 5434

# Container to host service (when needed)
redis:
  host: "host.docker.internal"  # For host-local Redis
  port: 6380
```

### Platform Notes
| Platform | Connection String |
|----------|-------------------|
| Linux Docker | `host.docker.internal` (requires `--add-host` flag) |
| Docker Desktop (Mac/Windows) | `host.docker.internal` (built-in) |
| CI/CD runners | `host.docker.internal` or service name |

### Docker Run Command
For Linux, add the host mapping:
```bash
docker run --add-host=host.docker.internal:host-gateway [image]
```

### Docker Compose
```yaml
services:
  app:
    image: chiseai-app
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Testing Inside Containers
When running tests inside a Docker container:
```python
# Get database host from environment or use default
DATABASE_HOST = os.getenv("DB_HOST", "host.docker.internal")
```

### **CRITICAL: Testing Dashboard/Container Endpoints**

**From this agent environment (which runs in a Docker container):**
- ✅ CORRECT: `curl http://host.docker.internal:8502/_stcore/health`
- ❌ WRONG: `curl http://localhost:8502/_stcore/health` (will fail - you're in a container!)

**From the host machine (laptop/desktop terminal):**
- ✅ CORRECT: `curl http://localhost:8502/_stcore/health`
- ❌ WRONG: `curl http://host.docker.internal:8502/_stcore/health` (host.docker.internal doesn't exist on host)

**Quick Reference:**
| Context | Test Dashboard Health |
|---------|----------------------|
| Agent environment (in Docker) | `curl http://host.docker.internal:8502/_stcore/health` |
| Host terminal | `curl http://localhost:8502/_stcore/health` |

**If neither works:**
1. Check if container is running: `docker ps --filter name=chise-dashboard`
2. Check container logs: `docker logs <container_name>`
3. Verify port mapping: `docker port <container_name>`
4. The error "File does not exist" means the Dockerfile or volume mount is wrong

---

## Docker Network Governance (MANDATORY)

### Authoritative Networks
**`chiseai`** is the authoritative Docker network for all ChiseAI services deployed via Terraform.

> **Note:** This change from chiseai2 to chiseai as the authoritative network was made per user override on 2026-01-21.

**Network Configuration (chiseai):**
- **Subnet:** `172.27.0.0/16`
- **Gateway:** `172.27.0.1`
- **State Source:** `infrastructure/terraform/terraform.tfstate` (authoritative)
- **Deployment Method:** Terraform IaC (see `infrastructure/terraform/`)

**Local Infra Stack (Terraform):**
- Definition path: `infrastructure/terraform/`
- Apply with: `terraform init` then `terraform apply`
- Services include Redis, Postgres, InfluxDB, Qdrant, Grafana, Gitea, Woodpecker, Taiga

**Pre-commit Hook Enforcement:**
- A pre-commit hook at `.git/hooks/pre-commit` runs `scripts/validate_docker_connectivity.py`
- **Blocks commits** if containers are created outside of `chiseai` network
- Exceptions must be explicitly approved by Captain Craig

### Protected Containers (NO TOUCH)
The following containers require **explicit permission from Captain Craig** before any modification:

| Container | Protection Level |
|-----------|-----------------|
| `tradedev` | **CRITICAL** - No modifications without explicit approval |
| `intelligent_ride` (MCP server) | Protected |
| `aisetup-mcp-discord-1` (MCP server) | Protected |
| `duckduckgo-mcp-server` (MCP server) | Protected |

### Authoritative Containers (Terraform-Deployed)
All ChiseAI services must be on `chiseai` network:

| Container Name | Network | Host Port | Container Port | Deployment |
|----------------|---------|-----------|----------------|-------------|
| `chiseai-redis` | chiseai | 6380 | 6380 | Terraform |
| `chiseai-postgres` | chiseai | 5434 | 5434 | Terraform |
| `chiseai-influxdb` | chiseai | 18087 | 18087 | Terraform |
| `chiseai-api-final` | chiseai | 8001 | 8001 | Terraform |
| `chiseai-qdrant` | chiseai | 6334 | 6334 | Terraform |
| `chise-dashboard` | chiseai | 8502 | 8502 | Terraform |
| `chiseai-grafana` | chiseai | 3001 | 3001 | Terraform |
| `gitea` | chiseai | 3000 | 3000 | Terraform |
| `woodpecker-server` | chiseai | 8012 | 8000 | Terraform |
| `woodpecker-agent` | chiseai | - | - | Terraform |
| `taiga-front` | chiseai | 9001 | 80 | Terraform |
| `taiga-back` | chiseai | 9002 | 8000 | Terraform |
| `taiga-events` | chiseai | 9003 | 8888 | Terraform |
| `taiga-postgres` | chiseai | - | 5432 | Terraform |
| `taiga-redis` | chiseai | - | 6379 | Terraform |
| `taiga-rabbitmq` | chiseai | - | 5672 | Terraform |

### Port Mapping Conventions
```yaml
# Standard port mappings for ChiseAI services
port_mapping:
  redis_server: '6380:6380'
  chiseai_postgres: '5434:5434'
  chiseai_influxdb: '18087:18087'
  chise_qdrant: '6334:6334'
  chiseai_api: '8001:8001'
  chise_dashboard: '8502:8502'
  chiseai_grafana: '3001:3001'
  gitea: '3000:3000'
  gitea_ssh: '2222:22'
  woodpecker: '8012:8000'
  taiga_front: '9001:80'
  taiga_back: '9002:8000'
  taiga_events: '9003:8888'
```

### Connectivity Exceptions
Limited exceptions to the `host.docker.internal` rule:

| Exception Context | Allowed Host | Reason | Scope |
|------------------|--------------|--------|-------|
| `dashboard_staging` | `localhost` | Testing new dashboard changes safely | `chise-dashboard` container only |

**All other services MUST use `host.docker.internal` for host service connections.**

### Creating Containers on chiseai Network
```bash
# CORRECT - Create on chiseai network
docker run --network chiseai --name my-service [image]

# CORRECT - Or add to existing network
docker network connect chiseai my-service

# ❌ WRONG - Will be blocked by pre-commit hook
docker run --network bridge --name my-service [image]
```

### Docker Compose with chiseai Network
```yaml
version: '3.8'
services:
  chiseai-api:
    image: chiseai-api
    networks:
      - chiseai

  chiseai-postgres:
    image: postgres:15
    networks:
      - chiseai

networks:
  chiseai:
    external: true
```

### Pre-commit Hook Validation
Before any commit:
```bash
# Automatically run via .git/hooks/pre-commit
python3 scripts/validate_docker_connectivity.py
```

**What the hook validates:**
- All running Docker containers are on the `chiseai` network
- Protected containers are not being modified without approval
- Exceptions are properly documented in the allowed list

**If validation fails:**
- Commit is blocked
- Review the output for which containers violate governance
- Fix by connecting containers to `chiseai` network or getting explicit approval

### Docker Label Standard

All ChiseAI containers MUST have the following label for identification and governance:

```yaml
labels:
  - "project=chiseai"
```

**Purpose:**
- Enables easy identification of ChiseAI containers across the infrastructure
- Supports automated governance and compliance checks
- Facilitates container inventory and management
- Enables filtering and querying of ChiseAI resources

**Implementation Requirements:**
- All containers deployed as part of ChiseAI services MUST include `project=chiseai` label
- Docker Compose services MUST define the label in their service configuration
- Terraform-deployed containers MUST set the label via container definitions
- Manual `docker run` commands MUST include `--label "project=chiseai"`

**Docker Compose Example:**
```yaml
version: '3.8'
services:
  chiseai-api:
    image: chiseai-api
    labels:
      - "project=chiseai"
    networks:
      - chiseai

  chiseai-postgres:
    image: postgres:15
    labels:
      - "project=chiseai"
    networks:
      - chiseai

networks:
  chiseai:
    external: true
```

**Docker Run Example:**
```bash
# CORRECT - Includes required label
docker run --network chiseai --label "project=chiseai" --name my-service [image]

# ❌ WRONG - Missing required label
docker run --network chiseai --name my-service [image]
```

**Validation:**
- The pre-commit hook `scripts/validate_docker_connectivity.py` verifies containers have the required label
- Containers without the `project=chiseai` label will fail validation
- Protected containers (tradedev, intelligent_ride, etc.) are exempt from this requirement
