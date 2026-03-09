---
name: "chise-full-pilot-run"
description: "ChiseAI: run Full Pilot phase loops (phase2 reflection/metacog/evolution wiring, phase3 guarded strategy autopilot, phase4 scorecard optimization)."
disable-model-invocation: true
---

## Run all phases (default)

```bash
python3 scripts/ops/full_pilot_phase_runner.py --phase all
```

## Dry-run all phases

```bash
python3 scripts/ops/full_pilot_phase_runner.py --phase all --dry-run
```

## Run single phase

```bash
python3 scripts/ops/full_pilot_phase_runner.py --phase phase2
python3 scripts/ops/full_pilot_phase_runner.py --phase phase3
python3 scripts/ops/full_pilot_phase_runner.py --phase phase4
```

## Artifacts

- Event log: `_bmad-output/full-pilot/events.jsonl`
- Scorecard JSON: `_bmad-output/full-pilot/scorecard.json`
- Scorecard Markdown: `_bmad-output/full-pilot/scorecard.md`
- Go/No-Go packet: `_bmad-output/full-pilot/go-no-go-packet.json`
