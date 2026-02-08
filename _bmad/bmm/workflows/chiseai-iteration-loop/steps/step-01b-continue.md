---
name: 'step-01b-continue'
description: 'Continue an existing ChiseAI iteration loop spec'

workflow_path: '{project-root}/_bmad/bmm/workflows/chiseai-iteration-loop'

thisStepFile: '{workflow_path}/steps/step-01b-continue.md'
nextStepFile: '{workflow_path}/steps/step-02-mem-scan.md'
workflowFile: '{workflow_path}/workflow.md'

outputFile: '{output_folder}/chiseai-iteration-loop-spec-{project_name}.md'
---

# Step 01b: Continue Existing Spec

## STEP GOAL:

Resume the workflow spec from the next unfinished step.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input, unless this step explicitly instructs auto-proceed routing
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

- 🎯 Focus only on continuation detection
- 🚫 FORBIDDEN to draft new sections in this step
- 💬 Approach: inspect frontmatter and determine the next step

## EXECUTION PROTOCOLS:

- 🎯 Read `stepsCompleted` from `{outputFile}` frontmatter
- 💾 Determine the next step in sequence
- 📖 Load the appropriate next step file

## CONTEXT BOUNDARIES:

- Available context: `{outputFile}` frontmatter
- Focus: continuation routing only
- Limits: no content edits in this step
- Dependencies: accurate `stepsCompleted`

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine next step

- Open `{outputFile}` and read `stepsCompleted`.
- Identify the next step in sequence after the highest completed step.

### 2. Present MENU OPTIONS

Display: "**Proceeding to the next incomplete step...**"

#### Menu Handling Logic:

- After determining the next step, immediately load, read entire file, then execute `{nextStepFile}`

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after routing

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the next step is identified, will you then load and read fully `{nextStepFile}` to execute.

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Correct next step identified
- Proper routing to next step file

### ❌ SYSTEM FAILURE:

- Proceeding without reading `stepsCompleted`
- Drafting content in a routing step
- Skipping auto-proceed instruction

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
