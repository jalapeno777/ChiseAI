# Add persona regression harness

## Objective
Create a weekly persona consistency suite with golden scenarios and drift scoring.

## Why this matters
No proven persona regression tests currently exist, so drift can happen silently.

## Scope
- add golden case file
- add rubric
- implement scorer or evaluation harness
- schedule weekly run

## Deliverables
- test suite assets
- initial runner or evaluation script
- weekly CI/scheduler hook

## Acceptance criteria
- Craig-mode and subagent-mode are both tested
- approval-boundary behavior is tested
- drift score is emitted
- failures are visible in CI/reporting

## Notes
Start simple with canonical cases before expanding into richer benchmark coverage.
