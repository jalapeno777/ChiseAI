---
name: "chise-pr-review-bot"
description: "ChiseAI: autonomous PR review + approve/deny using GitReviewBot + Gitea API"
disable-model-invocation: true
---

Follow these steps exactly (do not skip):

1. Preconditions
   - `GITEA_REVIEW_TOKEN` must be set (dedicated review-bot user; not the PR author).
   - You must know `PR_NUMBER` and `STORY_ID`.
   - CI should be green or actively running with a required context.

2. Run the review
   - Get two independent reviews in parallel:
     - `senior-dev`: technical correctness + tests + regression risk (approve/block)
     - `critic`: adversarial compliance + workflow/process + safety invariants (approve/block)
   - Then use `.opencode/agent/GitReviewBot.md` to synthesize:
     - APPROVE only if both independent reviews are non-blocking.
   - Outcome must be one of:
     - APPROVE
     - REQUEST_CHANGES

3. Post the review to Gitea
   - If APPROVE:
     - `python3 scripts/gitea_pr_review.py --pr <PR_NUMBER> --state APPROVED --body "<summary>"`
   - If REQUEST_CHANGES:
     - `python3 scripts/gitea_pr_review.py --pr <PR_NUMBER> --state REQUEST_CHANGES --body "<blocking issues + next steps>"`
     - Notify `jarvis` with the blocking issues and any suggested memory updates.

4. Evidence
   - Capture the review output and the command output in the story iterlog Evidence.
