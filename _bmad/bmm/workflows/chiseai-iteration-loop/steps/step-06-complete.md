---
name: 'step-06-complete'
description: 'Finalize the ChiseAI iteration loop spec'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-06-complete.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
---

# Step 06: Complete

## STEP GOAL:

Finalize the workflow spec and confirm completion.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a workflow executor and spec author
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ We engage in collaborative dialogue, not command-response
- ✅ You bring workflow structure expertise, user brings project context
- ✅ Maintain a clear, process-focused tone

### Step-Specific Rules:

- 🎯 Focus only on completion
- 🚫 FORBIDDEN to introduce new requirements
- 💬 Approach: append completion section and update frontmatter

## EXECUTION PROTOCOLS:

- 🎯 Append the completion section to `{outputFile}`
- 💾 Update `stepsCompleted` to include step 6
- 📖 Confirm completion to user

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}`
- Focus: completion only
- Limits: no new workflow sections
- Dependencies: output file exists

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Append completion section

Append the following section to `{outputFile}`:

```markdown
## Completion

The ChiseAI iteration loop workflow spec is complete. Use this workflow to enforce MEM-SCAN, acceptance criteria lock, Redis iteration logging, and memory promotion across Opencode agents and BMAD orchestrators.
```

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the completion section is appended and frontmatter updated, will the workflow be considered complete.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Completion section appended
- `stepsCompleted` includes step 6

### ❌ SYSTEM FAILURE:

- Missing frontmatter update
- Adding new requirements in completion step

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

