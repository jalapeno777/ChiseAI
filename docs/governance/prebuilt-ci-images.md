# Prebuilt CI Images

This repository uses prebuilt Docker images for most Woodpecker CI steps instead of installing Python tools at runtime.
The intent is to keep the CI pipeline fast, deterministic, and easy to reason about.

## Why We Use Prebuilts

The main reasons are:

- Avoid repeated `apt-get` and `pip install` work on every pipeline run.
- Keep gate runtime focused on the validation itself, not on environment setup.
- Make pipeline behavior more stable by fixing the toolchain in the image layer.
- Allow expensive dependency resolution to happen once during image creation instead of on every gate run.

This matters most for gates that are executed frequently or that pull in large dependency sets:

- `local-ci`
- `pre-eval-ingestion`
- `brain-eval`
- `dependency-audit`
- `format-check`
- `lint-check`

## Current Pattern

The current setup follows a small set of conventions:

1. Each image has a dedicated Dockerfile under `infrastructure/docker/`.
2. The image name uses the `chiseai-ci-*` prefix.
3. The image tag is versioned, typically with a Python and date suffix such as `py311-20260323`.
4. Woodpecker steps reference the prebuilt tag directly.
5. Runtime gate scripts assume the dependencies they need are already present in the image.

Examples:

- `infrastructure/docker/Dockerfile.ci-tools`
- `infrastructure/docker/Dockerfile.ci-lint`
- `infrastructure/docker/Dockerfile.ci-dependency-audit`
- `infrastructure/docker/Dockerfile.ci-local-ci`
- `infrastructure/docker/Dockerfile.ci-pre-eval-ingestion`
- `infrastructure/docker/Dockerfile.ci-brain-eval`

## How The Images Are Layered

The images are layered to minimize duplication:

- `chiseai-ci-tools` is the base CI toolbox.
- `chiseai-ci-lint` builds on the base toolbox and adds the formatting/linting stack used by the push gates.
- `chiseai-ci-dependency-audit` starts from Python slim and bakes the audit tooling plus the dependency snapshot used by the audit gate.
- `chiseai-ci-local-ci`, `chiseai-ci-pre-eval-ingestion`, and `chiseai-ci-brain-eval` build on the base toolbox and add only the packages those gates need.

This keeps the shared tooling in one place and prevents every specialized image from repeating the same baseline installs.

## Why Some Gates Audit Different Ways

`dependency-audit` is the only gate that deliberately uses a frozen dependency snapshot.

Why:

- The audit itself was spending too much time resolving dependencies at runtime.
- The image now precomputes the package set once.
- The runtime gate can audit the installed environment directly with `pip-audit -l --disable-pip`.

This preserves robustness because the audited set is still the actual installed environment in the prebuilt image.
The only thing moved out of CI runtime is the repeated resolution work.

## How To Change An Existing Image

Use this checklist:

1. Update the relevant `infrastructure/docker/Dockerfile.ci-*` file.
2. Keep the Dockerfile small and layer only the packages that gate actually needs.
3. Build the image locally with `docker build -f <Dockerfile> -t <tag> .`.
4. Verify the tag exists locally with `docker image ls`.
5. Update the matching Woodpecker step in `.woodpecker/ci.yaml` or `.woodpecker/push.yaml`.
6. Update the helper script in `scripts/ci/` if that image has a build wrapper.
7. Commit the Dockerfile and wiring together.

Notes:

- Prefer adding a new image only when a gate has a clearly different dependency profile.
- If a gate can reuse `chiseai-ci-tools`, prefer that over creating another specialized image.
- If you change the tag version, update both the Woodpecker config and the build helper default.

## How To Add A New Prebuilt Image

If a new gate needs a prebuilt image:

1. Start from the closest existing Dockerfile.
2. Decide whether the gate can share `chiseai-ci-tools` or needs a dedicated image.
3. Add a new `Dockerfile.ci-<gate-name>` under `infrastructure/docker/`.
4. Keep the image focused on the minimum toolset needed by the gate.
5. Build and test the image locally.
6. Add the image tag to the Woodpecker step.
7. Add or update a `scripts/ci/build_ci_<gate>_image.sh` helper if the repo uses one for that image family.

## What Not To Do

Do not:

- Add build jobs into the CI flow just to produce the prebuilt images.
- Use `python:3.11` directly in Woodpecker steps if the gate can run from a prebuilt image.
- Expand the image with unrelated tooling "just in case".
- Use `--no-deps` for security audits unless the audited input is already a frozen, exact-pinned snapshot.

## Operational Rules

- Keep image tags explicit and versioned.
- Rebuild images outside Woodpecker when the dependency set changes.
- Validate the Woodpecker YAML after retagging steps.
- Keep image changes and step wiring in the same commit when possible.

## Practical Change Examples

- If `format-check` needs a newer `black`, update `Dockerfile.ci-lint`, rebuild the image, and retag the `format-check` step to the new image tag.
- If `local-ci` adds a new test dependency, add it to `Dockerfile.ci-local-ci` and rebuild the `chiseai-ci-local-ci` tag.
- If `dependency-audit` needs to cover new packages, update the frozen snapshot logic in `Dockerfile.ci-dependency-audit` and keep the runtime script aligned.

## Summary

Prebuilt CI images are used to move slow, repetitive setup work out of the pipeline and into a controlled build step.
The result is a faster CI loop, more predictable gate behavior, and simpler Woodpecker jobs.

When changing them, prefer small image deltas, explicit versioned tags, and matching updates to the step wiring.
