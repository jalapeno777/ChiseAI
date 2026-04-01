# Aria Implementation Scaffold Pack

This pack is a **repo-ready starter scaffold** for adding stable personality, governed memory, belief mutation auditing,
daily digest notifications, and persona consistency testing to the current ChiseAI / OpenCode swarm.

## What this pack is
- recommended file/folder structure
- starter YAML/JSON schemas
- markdown specs for the swarm
- implementation prompts for Aria
- Phase 1 execution tickets

## What this pack is not
- not a claim that these exact paths already exist in the repo
- not a replacement for your current memory system
- not a blind rewrite plan

## Design assumptions
This scaffold assumes:
- the current system already uses Redis, Qdrant, tempmemories, reflection loops, belief storage, and governance modules
- persona behavior is currently distributed across prompts, docs, AGENTS, and agent files
- consolidation exists but is disabled
- Discord notification support exists but event coverage is incomplete
- persona consistency regression testing is not yet built
- a canonical final context assembly pipeline is not yet proven as one deterministic module

## Recommended drop-in locations
- `docs/aria/` for human-readable specs
- `config/aria/` for policy and contract YAML
- `schemas/aria/` for machine-readable event/test schemas
- `tests/persona/` for persona regression cases
- `tickets/aria-phase1/` for swarm execution tickets
- `prompts/aria/` for operator prompts to Aria

## Suggested implementation order
1. adopt the contract/policy files
2. wire belief mutation audit logging
3. wire notification policy
4. create final context assembly layer
5. enable consolidation in staged rollout
6. add persona regression suite
7. add lesson effectiveness tracking

## Bundle contents
- `repo-tree.txt`
- `docs/aria/*`
- `config/aria/*`
- `schemas/aria/*`
- `tests/persona/*`
- `tickets/aria-phase1/*`
- `prompts/aria/*`
