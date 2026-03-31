# Gitea CLI Setup

Use the official Tea CLI when Gitea MCP is unavailable or cannot complete a task.

## Install

Tea is available as an official release binary from the Gitea Tea release page:

```bash
curl -fsSL -o "$HOME/.local/bin/tea" \
  https://gitea.com/gitea/tea/releases/download/v0.12.0/tea-0.12.0-linux-amd64
chmod +x "$HOME/.local/bin/tea"
tea --version
```

If you prefer a source build, the upstream repository is `gitea.com/gitea/tea`, but the published module metadata can expose stale tags and some module installs are blocked by upstream `replace` directives. The release binary avoids that problem.

## Configure

Set the Gitea host and token in the environment before using Tea:

```bash
export GITEA_BASE_URL="http://host.docker.internal:3000"
export GITEA_TOKEN="..."
```

Some Tea commands also accept `GITEA_HOST`; keep the environment consistent with the target instance and document the exact command used when recording evidence.

## Usage policy

- Prefer Gitea MCP first for structured operations.
- Switch to `tea` when MCP is missing, unavailable, rate-limited, or cannot express the required action.
- Do not substitute random web UI clicks or raw API guessing when Tea can do the job.
- Capture the command, host, and auth context in the task evidence.
