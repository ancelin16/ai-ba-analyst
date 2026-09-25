# Architecture & Design Decisions

A running log of the key decisions: what was chosen, why, and what was traded
off. Each entry is written so it can be explained in an interview.

---

## D1. Staged pipeline instead of one large prompt
**Decision:** Split the analysis into separate AI calls (questions, problem, stakeholders, process, risks, requirements, stories, use cases, acceptance criteria, tests). Each call has its own prompt and output schema.

**Why:** A BA works in sequence. You understand the problem before writing requirements, and write requirements before tests. Each stage gets a focused prompt, is easier to test, and can be retried alone if it fails. Later stages receive the IDs produced by earlier ones, which is what makes traceability possible.

**Trade-off:** More API calls, so more latency and cost. This is mitigated by running independent stages in parallel and by caching results.

## D2. Design the data contract before the AI
**Decision:** Every artifact type is a Pydantic model (`app/models/`), written before any prompts.

**Why:** It's the same principle as defining requirements before building. The models state exactly what "a valid user story" or "a valid test case" means: required fields, ID formats, MoSCoW priorities. AI output that doesn't meet that definition is rejected, so it never reaches the user as broken content.

**Examples of rules enforced in code:**
- IDs follow fixed patterns (`FR-001`, `US-001`, `AC-001`, `TC-001`…) and must be unique within a list.
- A user story must reference at least one functional requirement.
- A **Critical** clarifying question must explain why it matters.
- Acceptance criteria must have all three of Given, When and Then.

## D3. "Basis" tag on every generated item
**Decision:** Objectives, requirements, stakeholders and constraints each carry a `basis` of **Stated**, **Inferred** or **Assumed**.

**Why:** The biggest risk with AI-generated requirements is invented facts that look authoritative. A BA must separate what the stakeholder said from what the analyst concluded. Making that separation a required field forces the model to classify each item, and the UI shows it so a reviewer knows what to confirm.

## D4. Lenient on format, strict on meaning
**Decision:** Enums accept formatting variants (`"must have"`, `"MUST_HAVE"` → `Must Have`) and unknown extra fields are ignored. Missing required content, wrong ID formats and unknown values are still rejected.

**Why:** Language models vary in capitalization and formatting. Rejecting a correct answer over formatting would cause needless retries. Rejecting a wrong answer protects quality.

## D5. Two-level input validation
**Decision:** Local checks run before any AI call. **Errors** block the run: empty input, over 6,000 characters, under 5 words. **Warnings** allow it but name what's missing: who is affected, why it matters, what's wanted. The AI does a deeper vagueness check in Stage 1.

**Why:** It's cheap, fast and deterministic, and it costs no API tokens on inputs that can't succeed. The warnings teach the user what a good request contains, which is a BA's elicitation job.

## D6. Environment-based configuration
**Decision:** The API key and model name come from environment variables or a git-ignored `.env` file. `Settings.__repr__` deliberately leaves out the key.

**Why:** Credentials must never be in source control or appear in logs or error traces.

## D7. Two layers of output checking: API structured outputs, then Pydantic
**Decision:** Each request sends the stage's JSON schema, generated from the Pydantic model with the SDK's `transform_schema`, as `output_config.format`. The API then guarantees the reply is valid JSON in that shape. The reply is still validated with Pydantic afterwards.

**Why:** The API guarantees the *structure* (field names, types, allowed values). Our *business rules* live in Pydantic: ID formats, unique IDs, a critical question must have a rationale, a story must cite a requirement. The two layers do different jobs.

## D8. One corrective retry, with the errors fed back
**Decision:** If a reply fails validation, the client sends it back with the exact validation errors and asks for a corrected version, once only. Network errors and rate limits are retried separately by the SDK's built-in backoff.

**Why:** Most validation failures are small and fixable, like a duplicated ID. Telling the model precisely what's wrong fixes them cheaply. Retrying more than once rarely helps and multiplies cost, so after two attempts the user gets a clear error instead.

## D9. Friendly errors mapped from specific SDK exceptions
**Decision:** Each Anthropic SDK exception maps to an application error with a plain-English `user_message`, e.g. "Your Anthropic account is out of credits", "Model X was not found".

**Why:** A business user can't act on a stack trace. A specific message tells them what to fix and whether retrying will help. Technical detail is kept separately for logs.

## D10. The AI sits behind an interface; tests use a fake
**Decision:** Pipeline code depends on an `LLMClient` protocol (a `generate()` method), not on the Anthropic SDK directly. Tests substitute a fake client or a stubbed SDK.

**Why:** Tests are fast (under 1 second), free and repeatable, and they can simulate failures that are hard to trigger for real: refusals, truncation, rate limits, malformed JSON. It also means another provider, or a local model, could be added later without touching the pipeline.

## D11. Stage 1 runs two calls in parallel
**Decision:** Clarifying questions and problem analysis are independent, so they run at the same time in two threads.

**Why:** Each call takes 15–25 seconds. Running them in parallel roughly halves the wait. Later stages depend on earlier outputs and can only be parallelised where they don't.

## D12. Model choice is configuration
**Decision:** The model is set by `CLAUDE_MODEL` in `.env`. The default is `claude-opus-5` for the best analysis quality. `claude-sonnet-5` costs about 60% less and was used for development runs. The first live Stage 1 run on Sonnet 5 used about 6.5K tokens, roughly $0.03 (full-analysis costs are in D17).

**Why:** Quality-versus-cost is a business decision that should be changeable without editing code.

## D13. Cross-stage references are checked during validation
**Decision:** Each stage receives the set of IDs it's allowed to cite (`known_ids`). If a user story cites `FR-099` and no FR-099 exists, validation fails, which triggers the corrective retry.

**Why:** A traceability matrix is only trustworthy if every link points at something real. Checking during generation fixes broken links at the source instead of only reporting them afterwards.

## D14. Coverage is a validation rule, and the prompt carries a checklist
**Decision:** Stages that must cover earlier artifacts get `must_cover` rules. Every in-scope requirement needs a story, every story needs acceptance criteria, and every criterion and every Must/Should requirement needs a test. The prompt also lists the exact IDs to cover. The requirements stage must produce at least one non-functional requirement.

**Why, with evidence:** On the first full live run, the model wrote **1 story for 9 requirements and 0 NFRs**. The deterministic traceability report caught it, with 7 High-severity gaps. After adding the rules and checklists, the next run produced 9 stories, 7 NFRs, 22 acceptance criteria and 27 tests, with **20 of 20 requirements fully traced and 0 gaps, all on the first attempt**. The checklist stops the model from stopping early, and the validation rule is the safety net if it still does.

**Interview angle:** "I didn't just trust the AI. I measured its output against a defined quality bar, found a gap, fixed it, and verified the fix."

## D15. The traceability matrix is built in code, not by the AI
**Decision:** `services/traceability.py` builds the matrix (objective → requirement → story → criterion → test) and the coverage-gap report with plain Python and pandas.

**Why:** Traceability is a factual question: is X linked to Y? Code answers it exactly and repeatably, while an AI might miss or invent links. It also works as an independent audit of the AI's output (see D14). "Won't Have" requirements are shown as out of scope and excluded from coverage metrics.

## D16. Stages save as they finish, and a failed run resumes
**Decision:** Each stage's result is stored on the `Analysis` as soon as it completes. If stage 5 fails, stages 1–4 are kept, and re-running continues from stage 5. Answering clarifying questions re-runs the problem analysis and clears everything downstream, because it all depends on that analysis.

**Why:** A full run is about 10 API calls and a few minutes. Losing all of it to one timeout would waste time and money.

## D17. Measured cost and duration
**Measured** on the order-tracking example with Sonnet 5: about 52K input and 40K output tokens per full analysis, **roughly $0.50** and **about 5 minutes**. Output includes the model's internal reasoning tokens. Opus 5 would cost roughly 2.5× as much. Future options if this matters: lower reasoning effort for the simpler stages, prompt caching of the shared system prompt, and streaming progress to the UI (Phase 4 shows per-stage progress).

## D18. Long lists are generated in small parallel batches
**Decision:** Acceptance criteria and test cases are generated two user stories at a time. The batches run in parallel and the results are merged and renumbered (AC-001, AC-002…). Non-functional-requirement tests join the last batch, or get their own batch when there are more than three.

**Why, with evidence:** On the 10-story sales-leads project, a single call covered only 2 of 10 stories, even with the checklist and a corrective retry. Debugging the raw API response showed it **ended normally** (not truncated, only about 2.6K output tokens) after roughly 10 list items. More instructions wouldn't fix that, so the unit of work had to shrink. After the change, acceptance criteria for all 10 stories completed in 47 seconds and the project reached **21 of 21 requirements fully traced with 62 test cases**. Parallel batches also cut wall-clock time.

**Trade-off:** Each batch re-sends the shared context, so input tokens rise, but input tokens cost a fifth as much as output tokens.

## D19. AI work runs as a job that survives page re-runs
**Decision:** A running analysis is stored in session state as a `Job` (thread, progress queue, result). Every page run first reattaches to any running job. Finishing work (saving, navigation) happens exactly once, in a callback. The sidebar is disabled while a job runs.

**Why:** Streamlit re-runs the whole page on any interaction. In live testing, one extra click during an analysis detached the progress display while the worker kept going, and a second click then started a duplicate run. That wasted API calls and left usage unrecorded. Found during end-to-end testing and covered by headless UI tests.

## D20. SQLite with plain SQL: summary columns plus a JSON document
**Decision:** The `analyses` table keeps the columns you'd list or filter on (name, status, model, timestamps) plus the full analysis as JSON. The `ai_calls` table logs every AI call. Every query uses `?` parameters, and a test tries a SQL-injection project name. A `CHECK` constraint limits `status` to known values, and `ON DELETE CASCADE` removes an analysis's usage rows along with it.

**Why:** The analysis is a deeply nested document, and normalizing it into a dozen tables would add complexity without a real query need. The usage log is naturally tabular, and SQL aggregates (`GROUP BY stage`, `SUM(tokens)`) answer the real business question "which step costs the most?"

## D21. Two export formats for two audiences
**Decision:** Word (.docx) is built from the structured data with real, editable tables, a cover note saying the draft needs stakeholder review, and repeating table headers. Markdown export and per-section copy use one shared renderer.

**Why:** BA deliverables are usually circulated as Word documents for comments and sign-off. Markdown pastes cleanly into Jira, Confluence and GitHub. Sharing one renderer means a section reads the same wherever it's copied to.
