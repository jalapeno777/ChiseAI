---
name: 'step-02-mem-scan'
description: 'Define MEM-SCAN rules for AGENTS.md discovery'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-02-mem-scan.md'
nextStepFile: '{workflow_path}/steps/step-03-acceptance-lock.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
---

# Step 02: MEM-SCAN (AGENTS.md Discovery)

## STEP GOAL:

Define forced AGENTS.md scanning rules to ensure local context is loaded before edits.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
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

- 🎯 Focus only on MEM-SCAN rules
- 🚫 FORBIDDEN to alter other workflow sections in this step
- 💬 Approach: append the MEM-SCAN section verbatim

## EXECUTION PROTOCOLS:

- 🎯 Append the MEM-SCAN section to `{outputFile}`
- 💾 Update `stepsCompleted` to include step 2
- 📖 Present menu and wait for user input

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}`
- Focus: MEM-SCAN rules only
- Limits: no other workflow sections
- Dependencies: output file exists

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Append MEM-SCAN section

Append the following section to `{outputFile}`:

```markdown
## MEM-SCAN: AGENTS.md Discovery Rules

**Trigger:** Before any edits, and after first file open within a new folder.

**Procedure:**
- Locate the nearest `AGENTS.md` by walking upward from the target file path.
- If none exists in the subtree, check repository root `AGENTS.md`.
- Record which `AGENTS.md` files were read in the iteration log.

**Opencode Behavior:**
- Do not edit files until MEM-SCAN is complete.
- If guidance conflicts, prefer folder-local AGENTS.md over root.
```

### 2. Present MENU OPTIONS

Display: "**Select an Option:** [C] Continue"

#### Menu Handling Logic:

- IF C: Save content to `{outputFile}`, update frontmatter, then only then load, read entire file, then execute `{nextStepFile}`
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#2-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C continue option] is selected and the MEM-SCAN section is appended, will you then load and read fully `{nextStepFile}` to execute and begin acceptance criteria lock.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- MEM-SCAN section appended
- `stepsCompleted` includes step 2
- Menu handled correctly

### ❌ SYSTEM FAILURE:

- Proceeding without user selection
- Missing frontmatter update
- Editing content outside MEM-SCAN scope

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

