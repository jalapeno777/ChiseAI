---
name: 'step-04-iteration-log'
description: 'Define Redis iteration log schema and lookup flow'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-04-iteration-log.md'
nextStepFile: '{workflow_path}/steps/step-05-memory-promotion.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
iterationTemplate: '{workflow_path}/templates/iteration-entry.json'
---

# Step 04: Redis Iteration Log

## STEP GOAL:

Define the Redis log structure, indexing keys, and TTL policy for iteration tracking.

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

- 🎯 Focus only on Redis iteration log rules
- 🚫 FORBIDDEN to alter other workflow sections in this step
- 💬 Approach: append the Redis log section verbatim

## EXECUTION PROTOCOLS:

- 🎯 Append the Redis log section to `{outputFile}`
- 💾 Update `stepsCompleted` to include step 4
- 📖 Present menu and wait for user input

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}`
- Focus: Redis iteration log only
- Limits: no other workflow sections
- Dependencies: output file exists

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Append Redis iteration log section

Append the following section to `{outputFile}`:

```markdown
## Redis Iteration Log (5-Day TTL)

**Primary Keys:**
- `bmad:chiseai:iterlog:story:<story_id>` (HASH) - latest snapshot
- `bmad:chiseai:iterlog:story:<story_id>:history` (LIST) - JSON entries

**Indexes:**
- `bmad:chiseai:iterlog:path:<path_slug>` (SET of story_ids)
- `bmad:chiseai:iterlog:agent:<agent_id>` (SET of story_ids)

**TTL:**
- Apply `EXPIRE 432000` (5 days) to all iterlog keys.
- Refresh TTL on each update.

**Path Slugging:**
- Use repo-relative path
- Lowercase; replace `/` with `:`
- Example: `src/neuro_symbolic/evolution` -> `src:neuro_symbolic:evolution`

**Iteration Entry Template:** `{iterationTemplate}`

**Lookup Flow:**
1) By story: `GET/HGETALL bmad:chiseai:iterlog:story:<story_id>`
2) By path: `SMEMBERS bmad:chiseai:iterlog:path:<path_slug>` -> story_ids -> read story hash
3) By agent: `SMEMBERS bmad:chiseai:iterlog:agent:<agent_id>` -> story_ids
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

ONLY WHEN [C continue option] is selected and the Redis iteration log section is appended, will you then load and read fully `{nextStepFile}` to execute and begin memory promotion rules.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Redis iteration log section appended
- `stepsCompleted` includes step 4
- Menu handled correctly

### ❌ SYSTEM FAILURE:

- Proceeding without user selection
- Missing frontmatter update
- Editing content outside Redis log scope

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.

