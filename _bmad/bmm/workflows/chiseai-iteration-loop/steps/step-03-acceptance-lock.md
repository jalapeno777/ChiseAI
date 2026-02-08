---
name: 'step-03-acceptance-lock'
description: 'Define acceptance criteria lock prior to implementation'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-03-acceptance-lock.md'
nextStepFile: '{workflow_path}/steps/step-04-iteration-log.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
acceptanceTemplate: '{workflow_path}/templates/acceptance-criteria.yaml'
---

# Step 03: Acceptance Criteria Lock

## STEP GOAL:

Define a pre-task acceptance criteria artifact that is independent of the final validation registry.

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

- 🎯 Focus only on acceptance criteria lock rules
- 🚫 FORBIDDEN to alter other workflow sections in this step
- 💬 Approach: append the acceptance criteria lock section verbatim

## EXECUTION PROTOCOLS:

- 🎯 Append the acceptance lock section to `{outputFile}`
- 💾 Update `stepsCompleted` to include step 3
- 📖 Present menu and wait for user input

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}`
- Focus: acceptance criteria lock only
- Limits: no other workflow sections
- Dependencies: output file exists

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Append acceptance lock section

Append the following section to `{outputFile}`:

```markdown
## Acceptance Criteria Lock (Pre-Work)

**Rule:** Each story must define acceptance criteria *before* implementation begins.

**Purpose:** Provide verifiable completion signals for the iteration loop. This is separate from `docs/validation/validation-registry.yaml`, which remains the final gate.

**Minimum Requirements:**
- Each criterion maps to one verification action (test, script, or manual check).
- Criteria must be specific, measurable, and binary (pass/fail).
- Each story must declare a `story_size` that fits in one iteration.

**Template:** Use `{acceptanceTemplate}` as the default structure.
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

ONLY WHEN [C continue option] is selected and the acceptance lock section is appended, will you then load and read fully `{nextStepFile}` to execute and begin Redis iteration log definition.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Acceptance lock section appended
- `stepsCompleted` includes step 3
- Menu handled correctly

### ❌ SYSTEM FAILURE:

- Proceeding without user selection
- Missing frontmatter update
- Editing content outside acceptance lock scope

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

