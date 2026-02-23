---
name: chiseai-docker-governance
description: Docker networking, container governance, and connectivity standards for ChiseAI infrastructure.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-docker-governance

## Goal

Ensure consistent Docker container networking and governance across ChiseAI infrastructure.

## When To Use

- Creating new containers
- Testing dashboard endpoints
- Debugging connectivity issues
- Infrastructure changes
- Deploying new services

## When Not To Use

- Application-level networking (use app-specific config)
- External service connections (use appropriate SDKs)
- Local development without Docker (no governance needed)
- Third-party containers outside ChiseAI scope

## Network Configuration

### Authoritative Network
- **Name**: `chiseai`
- **Subnet**: `172.27.0.0/16`
- **Gateway**: `172.27.0.1`

### From Agent Environment (Docker Container)
```bash
# ✅ CORRECT
curl http://host.docker.internal:8502/_stcore/health

# ❌ WRONG - won't work from inside container
curl http://localhost:8502/_stcore/health
```

### From Host Machine
```bash
# ✅ CORRECT
curl http://localhost:8502/_stcore/health

# ❌ WRONG - host.docker.internal doesn't exist on host
curl http://host.docker.internal:8502/_stcore/health
```

## Container Labels

All ChiseAI containers MUST have:
```yaml
labels:
  - "project=chiseai"
```

## Protected Containers

Require explicit Captain Craig approval:
- `tradedev`
- `intelligent_ride`
- `aisetup-mcp-discord-1`
- `duckduckgo-mcp-server`

## Pre-Commit Validation

Hook runs `scripts/validate_docker_connectivity.py` to check:
- All containers on `chiseai` network
- Required labels present
- No protected container modifications

## Exit Conditions

- Container connected to `chiseai` network.
- Required labels applied.
- Connectivity tested and verified.
- Protected container rules respected.

## Troubleshooting/Safety

- **Container can't reach host**: Use `host.docker.internal` instead of `localhost`.
- **Network not found**: Create `chiseai` network first: `docker network create chiseai`.
- **Label missing**: Add `--label "project=chiseai"` to docker run command.
- **Protected container touched**: Stop immediately, get Captain Craig approval.

## Related Skills

- `chiseai-validation` - Pre-commit hook integration
- `chiseai-memory-ops` - Redis container connectivity
- `chiseai-git-workflow` - Pre-commit workflow

## Related Commands

- `.opencode/command/chise-precommit-gates.md` - Validates Docker governance
