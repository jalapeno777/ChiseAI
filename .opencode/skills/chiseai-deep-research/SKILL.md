---
name: chiseai-deep-research
description: Systematic deep research methodology with multi-source synthesis, evidence grading, and structured deliverables.
metadata:
  version: "1.1"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-30"
---

# chiseai-deep-research

## Goal

Produce high-quality, evidence-backed research deliverables by enforcing a systematic methodology that avoids shallow analysis, premature conclusions, and hallucinated claims. Every finding must be traceable to a verified source.

## When To Use

- **"Research [topic] thoroughly"** — When the user asks for comprehensive research on any technical or domain topic
- **"I need a deep dive into [technology/concept]"** — When surface-level knowledge is insufficient
- **"Compare [A] vs [B] for [use case]"** — When multi-option analysis with evidence is needed
- **"What are the best practices for [domain]?"** — When industry-standard approaches must be identified
- **"Investigate [problem/solution space]"** — When exploring a problem space before architecture or strategy decisions
- **Pre-architecture research** — Before `chiseai-create-architecture` when domain understanding is incomplete
- **Pre-strategy research** — Before strategy DSL design when market/domain data is needed
- **Technical evaluation** — When evaluating tools, libraries, frameworks, or platforms for adoption

## Research Methodology

### Phase 1: Scope and Plan (Required)

Before gathering any data, define the research scope:

1. **Clarify the research question** — What specific question(s) must be answered?
2. **Define success criteria** — What would a complete answer look like?
3. **Identify source categories** — What types of sources are relevant? (docs, papers, benchmarks, community forums, code repos)
4. **Estimate depth** — Is this a quick survey (15-30 min), standard research (1-2 hours), or deep analysis (4+ hours)?
5. **Set evidence bar** — What level of evidence is required? (opinion, benchmark, peer-reviewed, production-proven)

### Phase 2: Multi-Source Discovery (Required)

Never rely on a single source. Use at least 3 distinct source categories:

1. **Primary sources** — Official documentation, API references, specification documents
2. **Community sources** — GitHub issues/discussions, Stack Overflow, Reddit, Discord
3. **Benchmark sources** — Performance comparisons, benchmark suites, real-world case studies
4. **Academic/industry sources** — Papers, whitepapers, conference talks, blog posts from domain experts

**Discovery tools:**

- Web search (`duckduckgo_search`, `ZAI_Search_web_search_prime`) for broad discovery
- Direct URL fetch (`ZAI_Reader_webReader`, `webfetch`) for specific documents
- Repository search (`ZAI_ZRead_search_doc`) for code-level insights
- Codebase search (`grep`, `glob`) for internal project context

### Phase 3: Evidence Grading (Required)

Grade every significant claim:

| Grade              | Meaning                                         | Required For                                     |
| ------------------ | ----------------------------------------------- | ------------------------------------------------ |
| **A-Verified**     | Confirmed by official docs or reproducible code | Architecture decisions, adoption recommendations |
| **B-Supported**    | Multiple independent sources agree              | Best practices, performance claims               |
| **C-Indicated**    | Single credible source, not contradicted        | Contextual background, trend analysis            |
| **D-Unverified**   | Single source, no corroboration                 | Only acceptable with explicit `D-grade` label    |
| **F-Contradicted** | Sources disagree or claim is refuted            | Must be noted as contested                       |

**Rules:**

- Never present a D-grade claim without its grade label
- If sources conflict, present all positions with their evidence grades
- If no A or B grade evidence exists for a key claim, flag it explicitly

### Phase 4: Synthesis and Deliverable (Required)

Produce a structured deliverable:

1. **Executive Summary** (required) — Key findings in 3-5 bullet points
2. **Detailed Findings** — Organized by topic/question, each with evidence grades
3. **Source Log** — Every source used with URL, access date, and relevance rating
4. **Gaps and Risks** — What could not be verified, what assumptions remain
5. **Recommendations** (when applicable) — Actionable next steps with confidence levels

## Rules

1. **No hallucination** — Every factual claim must have a source. If unsure, say "I could not verify this" with grade D.
2. **Depth over breadth** — Better to deeply understand 3 aspects than shallowly cover 10.
3. **Recency matters** — Prefer sources from the last 2 years unless analyzing historical context.
4. **Contradictions are valuable** — When sources disagree, document the disagreement rather than picking a side.
5. **Deliverable format** — Always produce a written deliverable, not just conversational answers.
6. **Time-box explicitly** — If research scope exceeds available time, narrow scope and state what was deferred.
7. **Cite inline** — Use `[source]` references throughout findings, linked to the Source Log.
8. **Separate facts from opinions** — Clearly label recommendations, opinions, and speculations as such.

## Integration with Other Skills

- **Before `chiseai-create-architecture`** — Use deep research to understand domain constraints and options
- **Before `chiseai-strategy-dsl-design`** — Use deep research to evaluate market patterns and approaches
- **Before `bmad-domain-research`** — Deep research can feed into formal domain research reports
- **Before `bmad-technical-research`** — Deep research provides the evidence base for technical research

## Anti-Patterns

- **Wikipedia-only research** — Starting and ending with Wikipedia or similar summaries
- **Confirmation bias** — Only searching for sources that support a pre-determined conclusion
- **Date-ignorant research** — Using outdated information for fast-moving technologies
- **Summary-only delivery** — Providing a brief summary without the detailed evidence backing it
- **Skipping the gap analysis** — Not acknowledging what could not be found or verified

## Exit Conditions

Stop and deliver early if:

- **Source exhaustion** — No new relevant sources found after 3 consecutive searches with varied queries
- **Time budget exceeded** — The estimated depth threshold was reached; narrow scope and deliver what was found
- **User redirects** — User explicitly changes scope or cancels the research mid-stream
- **Sufficient confidence** — All research questions have A or B grade evidence and success criteria are met
- **Contradiction dead-end** — Core claim has F-Contradicted evidence with no resolution path; flag and escalate

Always deliver a partial findings document rather than abandoning the research silently.

## Troubleshooting / Safety

| Problem                                 | Remedy                                                                                        |
| --------------------------------------- | --------------------------------------------------------------------------------------------- |
| Too many sources, drowning in data      | Narrow scope to top 3 most relevant questions; use evidence grading to prioritize A/B sources |
| All sources are D-grade                 | Flag explicitly; do not present as fact; recommend primary-source investigation               |
| Search tools return no results          | Try alternate query phrasing, broader terms, or different search tool                         |
| Sources contradict each other           | Present all positions with evidence grades; do not pick a side without A-grade evidence       |
| Research scope expanding uncontrollably | Time-box explicitly; document deferred items under Gaps and Risks                             |
| Hallucination risk (no sources found)   | State "I could not verify this" rather than fabricating; mark as D-grade                      |

## Related Skills

- **bmad-domain-research** — Formal domain/industry research report generation
- **bmad-technical-research** — Technology evaluation and architecture research
- **bmad-analyst** — Analyst agent for data interpretation
- **chiseai-data-first** — Enforce data gathering before analysis
- **chiseai-create-architecture** — Architecture design (post-research)
- **chiseai-strategy-dsl-design** — Strategy DSL design (post-research)
- **bmad-market-research** — Competitive and customer market research

## Related Commands

No dedicated commands. This skill is invoked by agent routing when the task matches "When To Use" triggers.

Use standard iteration commands for session management:

- `.opencode/command/chise-iterloop-start.md` — Start iteration tracking
- `.opencode/command/chise-iterloop-close.md` — Close iteration and promote learnings
