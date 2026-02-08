---
name: 'step-01-init'
description: 'Initialize ChiseAI iteration loop spec output and detect continuation'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-01-init.md'
nextStepFile: '{workflow_path}/steps/step-02-mem-scan.md'
continueStepFile: '{workflow_path}/steps/step-01b-continue.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
---

# Step 01: Initialize Workflow Spec

## STEP GOAL:

Create or resume the workflow specification document and capture baseline context.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input, unless this step explicitly instructs auto-proceed initialization
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a workflow executor and spec author
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ We engage in collaborative dialogue, not command-response
- ✅ You bring workflow structure expertise, user brings project context
- ✅ Maintain a clear, process-focused tone

### Step-Specific Rules:

- 🎯 Focus only on initializing or resuming the spec
- 🚫 FORBIDDEN to draft later sections in this step
- 💬 Approach: confirm file existence and initialize content

## EXECUTION PROTOCOLS:

- 🎯 Detect whether `{outputFile}` exists
- 💾 Create the output document if missing
- 📖 Ensure frontmatter includes `stepsCompleted: [1]`
- 🚫 Do not proceed until initialization is complete

## CONTEXT BOUNDARIES:

- Available context: workflow.md, config values, and `{outputFile}` if present
- Focus: initialization only
- Limits: no drafting of subsequent sections
- Dependencies: output file creation or continuation decision

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Check for existing output

- If `{outputFile}` exists, load and execute `{continueStepFile}`.
- If not, create `{outputFile}` with the following initial content:

```markdown
---
workflow: chiseai-iteration-loop
project: {project_name}
started: [current date]
stepsCompleted: [1]
---

# ChiseAI Iteration Loop Spec

## Purpose

Define the iterative implementation loop for ChiseAI with forced AGENTS.md scans, acceptance criteria locking, Redis iteration logs (TTL 5 days), and memory promotion rules.

## Scope

- Applies to Opencode agents and BMAD orchestrators
- Integrates with AGENTS.md and Redis
- Complements, but does not replace, validation registry gates
```

### 2. Present MENU OPTIONS

Display: "**Proceeding to MEM-SCAN definition...**"

#### Menu Handling Logic:

- After successful initialization, immediately load, read entire file, then execute `{nextStepFile}`

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after setup

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN initialization is complete, will you then load and read fully `{nextStepFile}` to execute and begin MEM-SCAN definition.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Output file created or continuation detected
- `stepsCompleted` includes step 1
- Ready to proceed to step 2

### ❌ SYSTEM FAILURE:

- Proceeding without initializing or detecting continuation
- Writing content beyond the initialization scope
- Skipping the auto-proceed instruction

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
