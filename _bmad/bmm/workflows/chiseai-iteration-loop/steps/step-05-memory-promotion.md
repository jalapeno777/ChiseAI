---
name: 'step-05-memory-promotion'
description: 'Define memory promotion rules across iteration log, AGENTS.md, and Qdrant'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-05-memory-promotion.md'
nextStepFile: '{workflow_path}/steps/step-06-complete.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
---

# Step 05: Memory Promotion Rules

## STEP GOAL:

Define when and how iteration learnings are promoted to AGENTS.md or Qdrant.

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

- 🎯 Focus only on memory promotion rules
- 🚫 FORBIDDEN to alter other workflow sections in this step
- 💬 Approach: append the memory promotion section verbatim

## EXECUTION PROTOCOLS:

- 🎯 Append the memory promotion section to `{outputFile}`
- 💾 Update `stepsCompleted` to include step 5
- 📖 Present menu and wait for user input

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}`
- Focus: memory promotion only
- Limits: no other workflow sections
- Dependencies: output file exists

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Append memory promotion section

Append the following section to `{outputFile}`:

```markdown
## Memory Promotion Rules

**Tier 1: Iteration Log (Redis)**
- Default sink for learnings during a story loop.
- Expires in 5 days unless refreshed.

**Tier 2: AGENTS.md (Local Context Memory)**
Promote from iteration log when the learning is:
- Folder-specific and likely to recur
- A constraint, invariant, or known hazard
- A local test/command requirement

**Tier 3: Qdrant (Long-Term Decisions/Patterns)**
Promote when the learning:
- Affects multiple subsystems
- Represents a design decision or anti-pattern
- Must persist beyond a sprint

**Promotion Trigger:**
- At story completion, assess iteration log for promotion candidates.
- Record promoted items and destinations in the iteration log entry.
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

ONLY WHEN [C continue option] is selected and the memory promotion section is appended, will you then load and read fully `{nextStepFile}` to execute and complete the workflow.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Memory promotion section appended
- `stepsCompleted` includes step 5
- Menu handled correctly

### ❌ SYSTEM FAILURE:

- Proceeding without user selection
- Missing frontmatter update
- Editing content outside memory promotion scope

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

