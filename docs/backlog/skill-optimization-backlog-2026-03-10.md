# Skill Optimization Backlog

**Generated:** 2026-03-10  
**Version:** 1.0  
**Status:** Active

---

## Executive Summary

This document tracks the optimization backlog for all 31 skills in the ChiseAI agent swarm. Skills are evaluated and optimized following the skill autonomy framework, with promotion to active status based on operational readiness.

### Current Status Overview

| Metric | Count |
|--------|-------|
| **Total Skills** | 31 |
| **PROMOTED** | 5 |
| **PENDING** | 26 |
| **P0 (Critical)** | 5 |
| **P1 (High)** | 14 |
| **P2 (Medium)** | 12 |

### Key Highlights

- **5 skills successfully promoted** to active status following evaluation
- **3 skills promoted from HOLD status** following opencode backend migration completion
- **26 skills remain pending optimization** across P0, P1, and P2 priorities
- **Estimated total effort:** ~95 story points for full optimization
- **Phased roadmap:** 5 phases over ~11 weeks

---

## Special Notice: Skills Promoted from HOLD

Three skills were originally on **HOLD** pending the opencode backend migration. These have now been **PROMOTED** following evaluation but require follow-up verification:

### chiseai-validation
- **Original Status:** HOLD
- **New Status:** PROMOTED
- **Reason:** Opencode backend migration completed; skill evaluated and promoted
- **Follow-up Required:** Verify validation commands work correctly with opencode backend (v1.1.60+)
- **Risk Level:** Low

### chiseai-skill-autonomy
- **Original Status:** HOLD
- **New Status:** PROMOTED
- **Reason:** Opencode backend migration completed; skill evaluated and promoted
- **Follow-up Required:** Verify tick/promote/rollback flows work with opencode backend
- **Risk Level:** Low

### chiseai-worker-contracts
- **Original Status:** HOLD
- **New Status:** PROMOTED
- **Reason:** Opencode backend migration completed; skill evaluated and promoted
- **Follow-up Required:** Verify contract validation works with opencode backend
- **Risk Level:** Low

---

## PROMOTED Skills (Already Optimized)

| Skill | Optimization Date | Category | Notes |
|-------|-------------------|----------|-------|
| **chiseai-git-workflow** | 2026-03-07 | Core | Git workflow standard for all swarm operations |
| **chiseai-metacognition-ops** | 2026-03-09 | Core | Metacognitive loops for decision quality |
| **chiseai-validation** | 2026-03-10 | Core | ⚠️ PROMOTED from HOLD - verify opencode integration |
| **chiseai-skill-autonomy** | 2026-03-10 | Core | ⚠️ PROMOTED from HOLD - verify tick flows |
| **chiseai-worker-contracts** | 2026-03-10 | Core | ⚠️ PROMOTED from HOLD - verify contract validation |

---

## P0 - CRITICAL PRIORITY (5 Skills)

These skills form the foundation for core swarm operations and block other optimization work.

| # | Skill | Effort | Dependencies | Category |
|---|-------|--------|--------------|----------|
| 1 | **chiseai-workflow-commands** | 5 pts | chiseai-git-workflow, chiseai-validation | Core Workflow |
| 2 | **chiseai-memory-ops** | 5 pts | - | Core Infrastructure |
| 3 | **chiseai-parallel-safety** | 4 pts | chiseai-memory-ops | Core Safety |
| 4 | **chiseai-incident-response** | 4 pts | chiseai-memory-ops, chiseai-git-workflow | Core Safety |
| 5 | **python-quality** | 3 pts | chiseai-validation | Core Quality |

### P0 Acceptance Criteria Summary

**chiseai-workflow-commands**
- [ ] All BMAD commands documented and tested
- [ ] Command routing logic verified
- [ ] Error handling robust
- [ ] Integration with validation layer working

**chiseai-memory-ops**
- [ ] Redis operations stable
- [ ] Qdrant vector search functional
- [ ] TTL and key patterns documented
- [ ] Fallback strategies implemented

**chiseai-parallel-safety**
- [ ] Scope ownership mechanism working
- [ ] Global locks implemented
- [ ] Incident handling procedures defined
- [ ] Redis-based ownership tracking functional

**chiseai-incident-response**
- [ ] Incident logging template complete
- [ ] Response procedures documented
- [ ] Post-mortem creation workflow tested
- [ ] Redis incident tracking functional

**python-quality**
- [ ] Black formatting rules configured
- [ ] Ruff linting setup
- [ ] Pytest coverage requirements defined
- [ ] Integration with CI gates working

---

## P1 - HIGH PRIORITY (14 Skills)

Important skills that support core operations and enable advanced workflows.

| # | Skill | Effort | Dependencies | Category | Blockers |
|---|-------|--------|--------------|----------|----------|
| 1 | **chiseai-sprint-cleanup** | 3 pts | chiseai-git-workflow, chiseai-branch-hygiene | Maintenance | chiseai-branch-hygiene |
| 2 | **chiseai-data-first** | 4 pts | - | Quality Gates | - |
| 3 | **chiseai-metrics-dashboard** | 3 pts | - | Observability | - |
| 4 | **chiseai-prd-quality** | 4 pts | chiseai-workflow-commands | Quality Gates | chiseai-workflow-commands |
| 5 | **chiseai-branch-hygiene** | 3 pts | chiseai-git-workflow, chiseai-memory-ops | Maintenance | chiseai-git-workflow |
| 6 | **chiseai-docker-governance** | 4 pts | - | Infrastructure | - |
| 7 | **chiseai-testing-patterns** | 4 pts | python-quality | Quality Gates | python-quality |
| 8 | **chiseai-skill-validation** | 3 pts | - | Quality Gates | - |
| 9 | **chiseai-risk-audit** | 4 pts | chiseai-validation, chiseai-worker-contracts | Safety | chiseai-validation, chiseai-worker-contracts |
| 10 | **chiseai-promotion-packet** | 3 pts | chiseai-git-workflow, chiseai-validation | CI/CD | chiseai-git-workflow |
| 11 | **chiseai-strategy-cicd-gates** | 5 pts | chiseai-validation, chiseai-promotion-packet, chiseai-turnover-metrics | CI/CD | Multiple |
| 12 | **chiseai-brain-cicd** | 5 pts | chiseai-validation, chiseai-promotion-packet | CI/CD | chiseai-validation |
| 13 | **chiseai-turnover-metrics** | 4 pts | - | Metrics | - |
| 14 | **chiseai-paper-trading-canary** | 4 pts | chiseai-strategy-cicd-gates, chiseai-turnover-metrics | CI/CD | chiseai-strategy-cicd-gates |

---

## P2 - MEDIUM PRIORITY (12 Skills)

Specialized and advanced skills that build upon core infrastructure.

| # | Skill | Effort | Dependencies | Category | Blockers |
|---|-------|--------|--------------|----------|----------|
| 1 | **chiseai-strategy-dsl-design** | 5 pts | chiseai-validation, chiseai-risk-audit | Advanced | chiseai-validation, chiseai-risk-audit |
| 2 | **webapp-testing** | 4 pts | - | Specialized | - |
| 3 | **theme-factory** | 3 pts | - | Specialized | - |
| 4 | **web-artifacts-builder** | 5 pts | theme-factory | Specialized | theme-factory |
| 5 | **frontend-design** | 5 pts | theme-factory, web-artifacts-builder | Specialized | theme-factory, web-artifacts-builder |
| 6 | **mcp-builder** | 5 pts | - | Specialized | - |
| 7 | **skill-creator** | 4 pts | chiseai-skill-validation | Meta | chiseai-skill-validation |

---

## Dependency Graph

### Root Skills (No Blockers)
- chiseai-memory-ops
- chiseai-git-workflow
- chiseai-validation

### Critical Path
```
chiseai-memory-ops
    ↓
chiseai-parallel-safety ←→ chiseai-worker-contracts
                                ↓
                        chiseai-workflow-commands
```

### Blocked by Validation Layer
- python-quality
- chiseai-testing-patterns
- chiseai-risk-audit
- chiseai-strategy-cicd-gates
- chiseai-brain-cicd

### Blocked by Memory Operations
- chiseai-parallel-safety
- chiseai-branch-hygiene
- chiseai-incident-response

---

## Optimization Roadmap

### Phase 1: Core Infrastructure (2 weeks)
**Skills:**
- chiseai-memory-ops (5 pts)
- chiseai-parallel-safety (4 pts)
- python-quality (3 pts)
- chiseai-incident-response (4 pts)

**Total Effort:** 16 story points

---

### Phase 2: Workflow Foundation (2 weeks)
**Skills:**
- chiseai-workflow-commands (5 pts)
- chiseai-branch-hygiene (3 pts)
- chiseai-data-first (4 pts)
- chiseai-prd-quality (4 pts)

**Total Effort:** 16 story points

---

### Phase 3: Quality & Maintenance (2 weeks)
**Skills:**
- chiseai-sprint-cleanup (3 pts)
- chiseai-testing-patterns (4 pts)
- chiseai-skill-validation (3 pts)
- chiseai-metrics-dashboard (3 pts)

**Total Effort:** 13 story points

---

### Phase 4: CI/CD Pipeline (2 weeks)
**Skills:**
- chiseai-turnover-metrics (4 pts)
- chiseai-promotion-packet (3 pts)
- chiseai-strategy-cicd-gates (5 pts)
- chiseai-brain-cicd (5 pts)
- chiseai-paper-trading-canary (4 pts)

**Total Effort:** 21 story points

---

### Phase 5: Advanced & Specialized (3 weeks)
**Skills:**
- chiseai-risk-audit (4 pts)
- chiseai-strategy-dsl-design (5 pts)
- chiseai-docker-governance (4 pts)
- webapp-testing (4 pts)
- theme-factory (3 pts)
- web-artifacts-builder (5 pts)
- frontend-design (5 pts)
- mcp-builder (5 pts)
- skill-creator (4 pts)

**Total Effort:** 39 story points

---

## Detailed Backlog Items

### chiseai-workflow-commands
- **Priority:** P0
- **Effort:** 5 story points
- **Dependencies:** chiseai-git-workflow, chiseai-validation
- **Category:** Core Workflow

**Acceptance Criteria:**
1. All BMAD commands documented and tested
2. Command routing logic verified
3. Error handling robust
4. Integration with validation layer working

**Notes:** Core skill for BMAD workflow execution. Required for planning/implementation/review commands.

---

### chiseai-memory-ops
- **Priority:** P0
- **Effort:** 5 story points
- **Dependencies:** None
- **Category:** Core Infrastructure

**Acceptance Criteria:**
1. Redis operations stable
2. Qdrant vector search functional
3. TTL and key patterns documented
4. Fallback strategies implemented

**Notes:** Foundation skill used by iteration loops and knowledge retention. Critical path for most skills.

---

### chiseai-parallel-safety
- **Priority:** P0
- **Effort:** 4 story points
- **Dependencies:** chiseai-memory-ops
- **Category:** Core Safety

**Acceptance Criteria:**
1. Scope ownership mechanism working
2. Global locks implemented
3. Incident handling procedures defined
4. Redis-based ownership tracking functional

**Notes:** Required for safe parallel agent execution. Dependencies on memory-ops for state tracking.

---

### chiseai-incident-response
- **Priority:** P0
- **Effort:** 4 story points
- **Dependencies:** chiseai-memory-ops, chiseai-git-workflow
- **Category:** Core Safety

**Acceptance Criteria:**
1. Incident logging template complete
2. Response procedures documented
3. Post-mortem creation workflow tested
4. Redis incident tracking functional

**Notes:** Critical for handling failures and learning from incidents. Required for production safety.

---

### python-quality
- **Priority:** P0
- **Effort:** 3 story points
- **Dependencies:** chiseai-validation
- **Category:** Core Quality

**Acceptance Criteria:**
1. Black formatting rules configured
2. Ruff linting setup
3. Pytest coverage requirements defined
4. Integration with CI gates working

**Notes:** Foundation for all Python code quality. Required by validation layer.

---

### chiseai-sprint-cleanup
- **Priority:** P1
- **Effort:** 3 story points
- **Dependencies:** chiseai-git-workflow, chiseai-branch-hygiene
- **Category:** Maintenance
- **Blockers:** chiseai-branch-hygiene

**Acceptance Criteria:**
1. Cleanup automation scripts working
2. Branch hygiene checks integrated
3. Main branch sync procedures tested
4. Pre-sprint validation complete

**Notes:** Important for repository hygiene before new sprints. Depends on branch hygiene.

---

### chiseai-data-first
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** None
- **Category:** Quality Gates

**Acceptance Criteria:**
1. Phase 0 data gathering checklist complete
2. Validation gates for data completeness
3. Integration with workflow commands
4. Documentation of data requirements

**Notes:** Enforces data-before-analysis workflow. Important for quality but not blocking other skills.

---

### chiseai-metrics-dashboard
- **Priority:** P1
- **Effort:** 3 story points
- **Dependencies:** None
- **Category:** Observability

**Acceptance Criteria:**
1. Grafana dashboard interaction patterns documented
2. Metrics reference guide complete
3. Query examples provided
4. Alert configuration guidance

**Notes:** Important for observability but standalone skill. Lower priority than core workflow.

---

### chiseai-prd-quality
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** chiseai-workflow-commands
- **Category:** Quality Gates
- **Blockers:** chiseai-workflow-commands

**Acceptance Criteria:**
1. PRD quality criteria defined
2. Traceability requirements specified
3. Success criteria templates
4. Integration with BMAD workflow

**Notes:** Raises PRD quality standards. Important for planning phase but depends on workflow-commands.

---

### chiseai-branch-hygiene
- **Priority:** P1
- **Effort:** 3 story points
- **Dependencies:** chiseai-git-workflow, chiseai-memory-ops
- **Category:** Maintenance
- **Blockers:** chiseai-git-workflow

**Acceptance Criteria:**
1. Branch lifecycle procedures documented
2. Cleanup automation working
3. Redis tracking for branch status
4. Stale branch detection implemented

**Notes:** Important for repository maintenance. Required by sprint-cleanup.

---

### chiseai-docker-governance
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** None
- **Category:** Infrastructure

**Acceptance Criteria:**
1. Network configuration standards documented
2. chiseai network requirements specified
3. Protected container list maintained
4. Port mapping conventions defined

**Notes:** Critical for infrastructure but lower priority than core workflow skills.

---

### chiseai-testing-patterns
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** python-quality
- **Category:** Quality Gates
- **Blockers:** python-quality

**Acceptance Criteria:**
1. Testing patterns documented
2. Coverage requirements specified
3. Pytest best practices defined
4. Integration with validation gates

**Notes:** Supports code quality. Important for all development work.

---

### chiseai-skill-validation
- **Priority:** P1
- **Effort:** 3 story points
- **Dependencies:** None
- **Category:** Quality Gates

**Acceptance Criteria:**
1. Skill structure validation rules defined
2. Frontmatter requirements specified
3. Required sections checklist
4. Automated validation working

**Notes:** Important for skill quality but not blocking initial optimization work.

---

### chiseai-risk-audit
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** chiseai-validation, chiseai-worker-contracts
- **Category:** Safety
- **Blockers:** chiseai-validation, chiseai-worker-contracts

**Acceptance Criteria:**
1. Risk constraints defined
2. POC-mode enforcement rules
3. Confidence thresholds specified
4. Audit procedures documented

**Notes:** Important for safe strategy recommendations. Depends on validation and contracts.

---

### chiseai-promotion-packet
- **Priority:** P1
- **Effort:** 3 story points
- **Dependencies:** chiseai-git-workflow, chiseai-validation
- **Category:** CI/CD
- **Blockers:** chiseai-git-workflow

**Acceptance Criteria:**
1. Promotion packet template complete
2. Evidence requirements specified
3. Risk assessment format defined
4. Rollback plan template

**Notes:** Supports strategy/brain promotion process. Important for CI/CD workflow.

---

### chiseai-strategy-cicd-gates
- **Priority:** P1
- **Effort:** 5 story points
- **Dependencies:** chiseai-validation, chiseai-promotion-packet, chiseai-turnover-metrics
- **Category:** CI/CD
- **Blockers:** Multiple dependencies

**Acceptance Criteria:**
1. Strategy selection criteria defined
2. Turnover gates specified
3. Promotion rules documented
4. backtest→paper→live workflow defined

**Notes:** Critical for strategy deployment pipeline. Multiple dependencies.

---

### chiseai-brain-cicd
- **Priority:** P1
- **Effort:** 5 story points
- **Dependencies:** chiseai-validation, chiseai-promotion-packet
- **Category:** CI/CD
- **Blockers:** chiseai-validation

**Acceptance Criteria:**
1. Brain versioning procedure defined
2. Evaluation framework specified
3. Shadow-test protocols documented
4. Human approval gates defined

**Notes:** Critical for brain upgrades. Similar to strategy-cicd-gates but for agent brain.

---

### chiseai-turnover-metrics
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** None
- **Category:** Metrics

**Acceptance Criteria:**
1. Turnover calculation formulas defined
2. Trades/day aggregation specified
3. avg/p95/max metrics documented
4. Reporting format established

**Notes:** Supports strategy evaluation. Required by strategy-cicd-gates.

---

### chiseai-paper-trading-canary
- **Priority:** P1
- **Effort:** 4 story points
- **Dependencies:** chiseai-strategy-cicd-gates, chiseai-turnover-metrics
- **Category:** CI/CD
- **Blockers:** chiseai-strategy-cicd-gates

**Acceptance Criteria:**
1. Canary deployment procedure defined
2. Trade budget enforcement rules
3. Promotion packet generation
4. Validation criteria specified

**Notes:** Important for safe strategy promotion. Depends on strategy CI/CD gates.

---

### chiseai-strategy-dsl-design
- **Priority:** P2
- **Effort:** 5 story points
- **Dependencies:** chiseai-validation, chiseai-risk-audit
- **Category:** Advanced
- **Blockers:** chiseai-validation, chiseai-risk-audit

**Acceptance Criteria:**
1. Strategy DSL schema defined
2. Parameter evolution rules specified
3. Structure auditability requirements
4. Safe evolution patterns documented

**Notes:** Advanced skill for strategy DSL design. Lower priority until core workflow stable.

---

### webapp-testing
- **Priority:** P2
- **Effort:** 4 story points
- **Dependencies:** None
- **Category:** Specialized

**Acceptance Criteria:**
1. Playwright testing patterns documented
2. Frontend verification procedures
3. UI debugging workflows defined
4. Screenshot capture guidelines

**Notes:** Specialized skill for web app testing. Not blocking core swarm operations.

---

### theme-factory
- **Priority:** P2
- **Effort:** 3 story points
- **Dependencies:** None
- **Category:** Specialized

**Acceptance Criteria:**
1. Theme system documented
2. 10 pre-set themes defined
3. Application procedures specified
4. Custom theme generation guide

**Notes:** Styling skill for artifacts. Nice-to-have for presentation.

---

### web-artifacts-builder
- **Priority:** P2
- **Effort:** 5 story points
- **Dependencies:** theme-factory
- **Category:** Specialized
- **Blockers:** theme-factory

**Acceptance Criteria:**
1. Multi-component artifact building guide
2. React/Tailwind integration documented
3. shadcn/ui usage patterns
4. State management examples

**Notes:** Advanced skill for complex HTML artifacts. Depends on theme-factory.

---

### frontend-design
- **Priority:** P2
- **Effort:** 5 story points
- **Dependencies:** theme-factory, web-artifacts-builder
- **Category:** Specialized
- **Blockers:** theme-factory, web-artifacts-builder

**Acceptance Criteria:**
1. Design quality standards defined
2. Component building patterns
3. Tailwind CSS best practices
4. UI/UX guidelines

**Notes:** Advanced frontend design skill. Builds on theme and artifacts skills.

---

### mcp-builder
- **Priority:** P2
- **Effort:** 5 story points
- **Dependencies:** None
- **Category:** Specialized

**Acceptance Criteria:**
1. MCP server design patterns documented
2. FastMCP usage guide (Python)
3. MCP SDK guide (Node/TypeScript)
4. Tool design best practices

**Notes:** Specialized skill for MCP server development. Important for integrations.

---

### skill-creator
- **Priority:** P2
- **Effort:** 4 story points
- **Dependencies:** chiseai-skill-validation
- **Category:** Meta
- **Blockers:** chiseai-skill-validation

**Acceptance Criteria:**
1. Skill creation workflow documented
2. Structure templates provided
3. Frontmatter requirements specified
4. Quality guidelines defined

**Notes:** Meta-skill for creating new skills. Depends on skill-validation.

---

## Appendix: Machine-Readable Format

A machine-readable YAML version of this backlog is available at:
```
docs/backlog/skill-optimization-backlog-2026-03-10.yaml
```

This file contains:
- Complete backlog items with all metadata
- Dependency graphs
- Roadmap phases
- Structured acceptance criteria

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-10 | 1.0 | Initial backlog creation |

---

*This document is maintained by the ChiseAI agent swarm. Updates should be tracked via the skill autonomy framework.*
