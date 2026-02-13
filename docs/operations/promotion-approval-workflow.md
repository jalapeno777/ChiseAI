# Promotion Approval Workflow

**Story:** ST-BT-003  
**Acceptance Criterion:** AC5 - Approval workflow is documented with required approvers and SLAs  
**Last Updated:** 2026-02-12

---

## Overview

This document defines the approval workflow for promoting canary strategies to paper full deployment. The workflow ensures human oversight of all promotion decisions with clear accountability, SLAs, and audit trails.

---

## Approval Workflow Stages

### Stage 1: Packet Generation

| Field | Value |
|-------|-------|
| Trigger | Canary duration threshold met (default: 7 days) |
| System Action | `PromotionPacketGenerator.generate_packet()` creates packet with status `pending` |
| Output | Markdown promotion packet with evidence, risk assessment, rollback plan |
| Location | `src/execution/canary/promotion.py` |

### Stage 2: Human Review

| Field | Value |
|-------|-------|
| Status | `pending` → `approved` or `rejected` |
| Required Action | Human approver reviews evidence and checks approval boxes |
| Decision Method | Explicit approval via checkboxes in Markdown packet |

### Stage 3: Decision Recording

| Field | Value |
|-------|-------|
| Approved | `PromotionPacket.approve(approver)` records approver ID and timestamp |
| Rejected | `PromotionPacket.reject(reason)` records rejection reason |
| Audit Trail | All decisions stored with full context in canary deployment record |

---

## Required Approvers

### Primary Approver

- **Role:** Human operator with paper trading authority
- **Responsibility:** Final approval decision on promotion
- **Requirements:**
  - Must review all evidence sections
  - Must check all approval boxes
  - Must provide approver identifier (name, ID, or role)

### Secondary Review (Optional)

- **Role:** Risk reviewer for high-drawdown or high-allocation promotions
- **Trigger Conditions:**
  - Allocation > 10% of portfolio
  - Max drawdown observed > 4%
  - Win rate < 50%
- **Responsibility:** Additional risk sign-off

---

## Service Level Agreements (SLAs)

| Stage | SLA | Escalation |
|-------|-----|------------|
| Packet Generation | Automatic when criteria met | N/A |
| Initial Review | 48 hours from packet generation | Auto-escalate to secondary reviewer |
| Re-review (after rejection) | 24 hours | Direct follow-up |
| Emergency Rollback | 15 minutes | Immediate page |

### SLA Monitoring

- Packets pending > 48 hours trigger reminder notification
- Packets pending > 72 hours escalate to secondary reviewer
- All SLA breaches logged for audit review

---

## Evidence Review Checklist

The following checklist mirrors the Markdown promotion packet template from `src/execution/canary/promotion.py`:

### Evidence Sections

- [ ] **Key Metrics Reviewed**
  - Duration threshold (default: 7 days)
  - Win rate threshold (default: 55%)
  - Max drawdown threshold (default: 5%)
  - Total trades count
  - Realized PnL

- [ ] **Gate Check Summary**
  - All gates passed verification
  - Individual gate results reviewed
  - Final evaluated status confirmed

- [ ] **Risk Assessment**
  - Drawdown risk level understood
  - Win rate stability considered
  - Sample size adequacy evaluated
  - Allocation impact assessed

- [ ] **Rollback Plan**
  - Rollback target identified
  - Rollback steps reviewed
  - Verification steps understood

### Approval Checkboxes

From the Markdown packet template (lines 378-380 in `promotion.py`):

```markdown
- [ ] I have reviewed the evidence
- [ ] I understand the risks
- [ ] I approve promotion to paper full

**Approved By:** _________________  
**Date:** _________________
```

---

## Rollback Procedure Reference

### Trigger Conditions

- Human rejection decision
- Performance degradation detected post-promotion
- Risk threshold breach

### Rollback Steps

From `PromotionPacket.rollback_plan` (defined in `promotion.py`):

1. Halt new position openings for candidate strategy
2. Close existing positions at market or next signal
3. Activate champion strategy for new signals
4. Verify champion is receiving and processing signals
5. Update registry to reflect rollback

### Verification Steps

- Confirm no pending orders for candidate
- Confirm champion is generating signals
- Verify portfolio state consistency

### Estimated Rollback Time

- **Target:** 5 minutes
- **Verification:** Additional 2-5 minutes

---

## Audit Trail Requirements

### Required Audit Fields

Every promotion packet must record:

| Field | Source | Retention |
|-------|--------|-----------|
| `packet_id` | Auto-generated UUID | 2 years |
| `canary_id` | Canary deployment reference | 2 years |
| `strategy_id` | Strategy being promoted | 2 years |
| `status` | `pending`, `approved`, `rejected` | 2 years |
| `generated_at` | Unix timestamp | 2 years |
| `approved_at` | Unix timestamp (if approved) | 2 years |
| `approved_by` | Approver identifier | 2 years |
| `rejection_reason` | Human-provided reason (if rejected) | 2 years |

### Audit Storage

- Primary: Canary deployment record in database
- Backup: Markdown packet file in `docs/approvals/promotion-packets/`
- Archive: Quarterly export to cold storage

### Audit Review

- Monthly review of approval patterns
- Quarterly SLA compliance report
- Annual audit of rollback frequency and reasons

---

## Bypass/Testing Process

### Testing Approvals

For CI/CD testing and development, a testing bypass is available:

**Bypass Conditions:**
- Running in test environment (`ENV=test`)
- Automated testing via `PromotionPacket.approve(test_approver)`
- Explicit test flag in configuration

**Audit Requirements for Bypass:**
1. All test approvals logged with `test_approver` identifier
2. Test packets marked with `test_mode: true` metadata
3. Test packet IDs prefixed with `test-`
4. Test approvals excluded from SLA calculations
5. Monthly report of test approvals generated

### Example Test Approval

```python
# In test environment only
packet = PromotionPacket(
    packet_id="test-packet-001",
    canary_id="test-canary-001",
    strategy_id="test-strategy-001",
    status="pending",
)
packet.approve("test_approver")  # Sets status to approved
assert packet.status == "approved"
assert packet.approved_by == "test_approver"
```

### Production Bypass (Emergency)

**POLICY:** No production bypass without explicit human authorization.

- Emergency bypass requires verbal approval from two authorized persons
- Bypass reason must be documented in writing within 24 hours
- Post-incident review required within 7 days
- All emergency bypasses logged to incident report

---

## References

- **Promotion Packet Code:** `src/execution/canary/promotion.py`
- **Canary Models:** `src/execution/canary/models.py`
- **Gate Evaluator:** `src/execution/canary/gate_evaluator.py`
- **Story:** ST-BT-003 - Paper Trading Canary System
- **Related:** ST-BT-001 (Canary Metrics Collection), ST-BT-002 (Gate Evaluation)

---

## Appendix: Promotion Packet Structure

From `PromotionPacket` dataclass in `src/execution/canary/promotion.py`:

```python
@dataclass
class PromotionPacket:
    packet_id: str              # Unique packet identifier
    canary_id: str              # Reference to canary deployment
    strategy_id: str            # Strategy being promoted
    champion_strategy_id: str   # Current champion strategy
    status: str                 # pending/approved/rejected
    evidence: PromotionEvidence # Collected metrics
    risk_assessment: dict       # Risk summary
    rollback_plan: dict        # Rollback details
    generated_at: int          # Unix timestamp
    approved_at: int           # Unix timestamp (if approved)
    approved_by: str           # Approver identifier (if approved)
    metadata: dict              # Additional context
```

---

*Document auto-generated for ST-BT-003 AC5 compliance*
