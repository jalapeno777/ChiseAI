---
name: "chise-skill-create"
description: "ChiseAI: scaffold a new skill and initialize eval fixtures for iterative optimization."
disable-model-invocation: true
---

Use this to create a new skill with an eval-ready layout.

1. Create the skill scaffold
   - Run:
     ```bash
     python3 scripts/ops/skill_creator/scripts/init_skill.py <skill_name> --path .opencode/skills
     ```

2. Quick-validate structure
   - Run:
     ```bash
     python3 scripts/ops/skill_creator/scripts/quick_validate.py .opencode/skills/<skill_name>
     ```

3. Create eval prompt set
   - Create directory:
     ```bash
     mkdir -p .opencode/skills/<skill_name>/evals
     ```
   - Create file `.opencode/skills/<skill_name>/evals/evals.json`:
     ```json
     {
       "skill_name": "<skill_name>",
       "evals": [
         {
           "id": 1,
           "prompt": "<realistic user query>",
           "expected_output": "<human-readable success condition>",
           "files": [],
           "expectations": []
         }
       ]
     }
     ```

4. Optional packaging check
   - Run:
     ```bash
     python3 scripts/ops/skill_creator/scripts/package_skill.py .opencode/skills/<skill_name>
     ```

Notes:
- Keep eval prompts realistic and task-specific.
- Use `.opencode/command/chise-skill-trigger-optimize.md` after baseline evals exist.
