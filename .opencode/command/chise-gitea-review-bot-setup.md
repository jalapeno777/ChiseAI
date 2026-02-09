---
name: "chise-gitea-review-bot-setup"
description: "ChiseAI: one-time setup for a dedicated Gitea review bot user/token"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Create a dedicated Gitea user
   - Example username: `chise-review-bot`
   - Rationale: Gitea disallows approving your own pull request.

2. Grant repo permissions
   - Ensure the user can access `craig/ChiseAI` and submit PR reviews.

3. Create a Personal Access Token (PAT) for the review bot
   - Required capabilities: submit PR reviews (approval / request changes).
   - Store it locally (do not commit).

4. Configure local environment
   - Put the PAT in `.env` (gitignored) as:
     - `GITEA_REVIEW_TOKEN=...`
   - Keep `GITEA_TOKEN` as the author/automerge token.

5. Sanity check
   - Post an approval on a non-self PR:
     - `python3 scripts/gitea_pr_review.py --pr <num> --state APPROVED --body "review-bot approval"`

