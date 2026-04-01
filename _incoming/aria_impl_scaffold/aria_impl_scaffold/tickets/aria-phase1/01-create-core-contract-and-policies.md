# Create core identity contract and policy files

## Objective
Introduce machine-readable identity and governance policy files as the source of truth for Aria's core behavior boundaries.

## Why this matters
Current behavior is distributed across prompts, docs, and agent files. The swarm needs a canonical contract to reduce persona drift and policy ambiguity.

## Scope
- add `config/aria/identity-contract.yaml`
- add `config/aria/governance-policy.yaml`
- add `config/aria/notification-policy.yaml`
- add `config/aria/context-budget-policy.yaml`
- wire loaders or parsing helpers

## Deliverables
- files created and validated
- parser or loader entry point
- README or inline docs describing each file

## Acceptance criteria
- contract loads without runtime error
- approval-gated fields are machine-detectable
- context priority order is machine-readable
- notification policy is machine-readable

## Notes
Merge with existing config modules if equivalent policy files already exist.
