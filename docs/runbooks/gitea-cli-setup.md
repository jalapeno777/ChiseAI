# GitHub CLI Setup (gh)

> **Note:** Gitea and Woodpecker are deprecated. GitHub is now the canonical SCM and CI platform.
> This runbook replaces the former `gitea-cli-setup.md`.

## Repository

- **GitHub:** https://github.com/jalapeno777/ChiseAI
- **Local remote name:** `github`

## Setup

### 1. Install GitHub CLI

```bash
# macOS
brew install gh

# Linux (Debian/Ubuntu)
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli-stable.list > /dev/null
sudo apt update && sudo apt install gh
```

### 2. Authenticate

```bash
gh auth login
# Follow prompts — select GitHub.com, HTTPS, authenticate with browser or token
```

### 3. Set the `github` remote (if not already set)

```bash
git remote add github https://github.com/jalapeno777/ChiseAI.git
# Or if switching from origin:
# git remote rename origin gitea-backup
# git remote add github https://github.com/jalapeno777/ChiseAI.git
```

## Common Commands

```bash
# List PRs
gh pr list --repo jalapeno777/ChiseAI

# Create a PR (after pushing branch to github remote)
gh pr create --repo jalapeno777/ChiseAI --title "ST-XXX: description" --body "Description"

# Check CI status
gh run list --repo jalapeno777/ChiseAI --limit 10

# View failed run logs
gh run view <run-id> --repo jalapeno777/ChiseAI --log

# Merge a PR (requires appropriate permissions)
gh pr merge <pr-number> --repo jalapeno777/ChiseAI --squash
```

## Deprecated: Gitea CLI (tea)

The Gitea instance and Woodpecker CI are deprecated. If you need historical access:

```bash
# tea CLI is no longer maintained for this project
# Use 'gh' for all SCM operations
```
