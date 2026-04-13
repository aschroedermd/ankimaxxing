# Anki Rewriter Plan

## Purpose

Build a standalone web application that augments existing Anki notes with semantically equivalent prompt variations while preserving Anki’s native scheduling. The application should also provide deck-wide AI-assisted factual review so users can audit cards for possible errors even when they do not want to generate rewrites.

This project is **not** an Anki replacement and should **not** create duplicate cards for scheduling purposes. The same underlying Anki card should continue to own its spaced-repetition history, while the displayed prompt is varied at render time.

---

## Core Product Goals

1. Load a target deck or filtered subset of notes from Anki.
2. Determine which field(s) are used as the prompt for each card template.
3. Generate multiple semantically equivalent rewrites for the prompt side only.
4. Preserve answer meaning, difficulty, and important technical details.
5. Randomize among precomputed prompt variants at review time without creating extra Anki cards.
6. Validate generated variants by default.
7. Offer a separate deck-audit mode that evaluates card accuracy without generating rewrites.
8. Support multiple LLM providers through a clean provider abstraction.
9. Be safe around common Anki note types, especially Basic, Basic-and-reversed, and Cloze.
10. Be reversible, inspectable, and conservative when modifying Anki note types or card templates.

---

## Most Important Architectural Conclusions

### 1. Keep Anki scheduling intact

The application should operate at the **note/template layer**, not by creating duplicate cards. A card’s interval, ease, and learning history must remain attached to the original Anki card.

### 2. Do not rely on Anki to randomize variants natively

Anki does not provide a built-in “pick one of these variants each review” feature. The practical way to do this is to store generated variants in note fields and use card-template JavaScript to choose which one is shown.

### 3. Front/back consistency must be designed explicitly

A random choice made on the prompt side must remain the same when the answer side is shown. A simple `Math.random()` on both sides will break the card. The robust plan is to persist the selected variant ID between front and back using a cross-platform persistence strategy rather than a desktop-only JS variable.

### 4. Avoid exploding the number of Anki fields

Instead of creating many fields like `VariantFront1`, `VariantFront2`, `VariantFront3`, the cleaner design is to add a **small number of app-owned fields** and store structured JSON there. This reduces note-type clutter and makes regeneration/versioning easier.

### 5. Avoid directly mutating user note types unless necessary

The safest approach is to **clone supported note types into app-managed variants** when template surgery is needed. Directly editing heavily customized user note types risks breakage and support nightmares.

### 6. Cloze handling must be token-aware, not plain-text paraphrasing

The app should protect `{{cN::...}}` spans and only rewrite the surrounding context. Cloze deletions must survive exactly.

### 7. Validation should be separated into two concerns

There are two different checks:

- **Variant fidelity validation**: is the generated rewrite still asking for the same answer?
- **Card factual audit**: is the original card itself accurate or suspect?

These should be modeled separately in prompts, storage, and UI.

---

## Recommended High-Level Architecture

```text
Frontend (Next.js / React / TypeScript)
  ├─ Deck browser
  ├─ Rewrite job configuration
  ├─ Variant review / approval UI
  ├─ Deck audit dashboard
  └─ LLM provider settings

Backend (Python / FastAPI)
  ├─ Anki client layer
  ├─ Note-type introspection layer
  ├─ Card understanding engine
  ├─ Rewrite orchestration engine
  ├─ Validation / audit engine
  ├─ Template patch manager
  ├─ Metadata / cache store
  └─ Job queue / worker layer

Anki integration
  ├─ AnkiConnect for reading / updating notes
  ├─ Model field/template introspection
  └─ App-managed template patches and note fields
```

---

## Why the Earlier Plan Should Be Improved

The earlier outline was directionally right, but these changes make it stronger:

### Modification A: Prefer a compact JSON field design

Earlier thinking assumed one field per variant. That works, but it scales poorly and makes note types messy. A better design is:

- `AIRewriteData`
- `AIRewriteMeta`
- `AIValidationData`

Where `AIRewriteData` stores structured JSON keyed by card template name and source field name.

Example conceptual structure:

```json
{
  "schema_version": 1,
  "fields": {
    "Front": {
      "variants": [
        {
          "id": "front-v1",
          "style": "conservative",
          "text": "...",
          "validation": {
            "semantic_match": "accurate"
          }
        }
      ]
    },
    "Back": {
      "variants": []
    }
  },
  "templates": {
    "Card 1": {
      "prompt_field": "Front",
      "answer_field": "Back"
    },
    "Card 2": {
      "prompt_field": "Back",
      "answer_field": "Front"
    }
  }
}
```

This is more future-proof than adding many individual fields.

### Modification B: Add a template patch manager as a first-class subsystem

Template modification is risky enough that it deserves its own module, versioning strategy, and rollback plan.

Responsibilities:
- detect whether a note type is already app-managed
- clone supported note types when needed
- insert app script/hooks in a controlled way
- preserve existing template logic where possible
- support rollback and reapply operations

### Modification C: Distinguish note-level rewrites from card-template-level prompt usage

A single note can produce multiple cards. For example, Basic (and reversed card) uses both `Front` and `Back` as prompts on different card templates. Rewrites should therefore be attached to the **field actually shown as the prompt for a given template**, not to the note in a simplistic front/back-only way.

### Modification D: Use a portable persistence strategy for randomization

Desktop-only tricks like `card.someValue = ...` are not robust enough across clients. A better plan is to use a tested persistence pattern that works with desktop, AnkiWeb, iOS, and AnkiDroid when possible.

### Modification E: Make “unsupported note type” a first-class outcome

The app should not pretend every custom template can be safely rewritten. The system should categorize cards as:
- supported
- supported with caution
- unsupported for rewrite but eligible for audit
- unsupported entirely

That keeps behavior honest and debuggable.

### Modification F: Add a human review gate for template patching

Even if rewrite generation can be automated, template changes are important enough that the first time a note type is patched, the app should show a preview and require explicit approval.

---

## Recommended Data Model

### In Anki (app-owned fields)

Prefer a small number of fields added to the target note type or cloned note type:

- `AIRewriteData`
- `AIRewriteMeta`
- `AIValidationData`
- optionally `AIRewriteStatus`

### In app database

Use a local SQLite database for app-side indexing, jobs, logs, and rollback metadata.

Suggested tables:

- `collections`
- `note_types`
- `template_patches`
- `notes`
- `rewrite_jobs`
- `note_rewrites`
- `validation_runs`
- `provider_profiles`
- `prompt_versions`
- `app_events`

### Why both Anki fields and app DB?

- **Anki fields** keep the review-time data portable with the deck itself.
- **App DB** keeps operational state, logs, prompt versions, rollback records, job progress, and analytics out of Anki.

---

## Anki Integration Strategy

### Primary integration: AnkiConnect

Use AnkiConnect as the initial and primary integration mechanism.

The backend should rely heavily on these capabilities:
- finding notes by deck/query
- fetching note fields and note type information
- discovering model field names
- discovering which fields are used on each card template
- updating note fields

### Important design implication

Use AnkiConnect to **introspect first**, then only patch compatible note types.

### Note-type safety policy

Recommended order of operations:
1. Inspect note type.
2. Classify support level.
3. Offer to clone note type into an app-managed derivative if patching is required.
4. Add app-owned fields.
5. Patch templates.
6. Update note field content.

### Why clone instead of mutate in place?

Because users may have:
- complex CSS
- existing JavaScript
- add-on-specific field expectations
- shared/community note types they do not want altered

A cloned note type like `Basic (AI Rewriter)` is much safer to support than silently modifying an existing `Basic` variant used by other workflows.

---

## Supported Note Types and Rewrite Rules

### 1. Basic

Typical structure:
- prompt field: `Front`
- answer field: `Back`

Rewrite target:
- `Front`

### 2. Basic (and reversed card)

Typical structure:
- `Card 1`: prompt = `Front`, answer = `Back`
- `Card 2`: prompt = `Back`, answer = `Front`

Rewrite target:
- both `Front` and `Back` can be rewritten, but independently, because each is a prompt on a different card template.

### 3. Basic (optional reversed card)

Treat like the above, but only patch the prompt field used by cards that actually exist.

### 4. Cloze

Typical structure:
- source field contains cloze markup
- prompt is generated from the field through cloze rendering

Rewrite target:
- the surrounding sentence/context only

Protected content:
- exact cloze tokens
- nested cloze syntax if present
- critical formatting and media references

### 5. Image occlusion / image-heavy / heavily scripted custom note types

Default policy:
- usually audit-only
- rewrite disabled unless a dedicated handler is implemented

### 6. Unknown custom note types

Handle conservatively.

Possible outcomes:
- fully supported
- partially supported (audit only)
- unsupported pending user review

---

## Card Understanding Engine

This subsystem should convert raw note/template information into a structured intermediate representation.

Suggested responsibilities:

1. Determine which field(s) are shown on the front of each card template.
2. Determine which of those are likely rewrite candidates.
3. Detect cloze syntax and protected spans.
4. Normalize HTML/text for LLM consumption.
5. Build a structured object for rewriting and validation.

Example conceptual intermediate representation:

```json
{
  "note_id": 123,
  "model_name": "Basic (and reversed card)",
  "template_name": "Card 2",
  "prompt_field": "Back",
  "answer_field": "Front",
  "prompt_raw": "...",
  "answer_raw": "...",
  "prompt_plain": "...",
  "answer_plain": "...",
  "content_type": "html",
  "card_kind": "reverse",
  "rewrite_mode": "field_rewrite",
  "protected_spans": []
}
```

---

## Rewrite Generation Design

### User-configurable controls

The user should be able to choose:
- number of variants
- aggressiveness distribution
- provider/model profile
- whether validation is on
- whether to require human approval before writeback

### Default distribution rules

User preference already established:
- if 2 variants: default to moderate + aggressive
- otherwise: default to a near-even split among conservative, moderate, aggressive

### Rewrite prompt principles

Every rewrite prompt should:
- include both prompt and answer
- specify which side may be rewritten
- prohibit semantic drift
- preserve difficulty and key technical distinctions
- preserve placeholders, media references, markup, and cloze spans when applicable
- return machine-parseable output

### Three rewrite styles

#### Conservative
Very close paraphrase; smallest semantic and structural movement.

#### Moderate
Meaning-preserving rewording that changes syntax and phrasing more visibly.

#### Aggressive
Still semantically aligned, but with more conceptual re-expression, alternative framing, or different sentence structure.

### Strong recommendation

Use **separate prompt templates per rewrite mode** rather than only changing a single adjective in one prompt. This yields more controllable outputs.

---

## Validation Design

### A. Variant fidelity validation (default on)

Purpose:
Determine whether a generated rewrite still tests the same knowledge as the original card.

Rating scale:
- `accurate`
- `probably accurate`
- `possibly inaccurate`
- `likely inaccurate`
- `wrong / definitely inaccurate`

Recommended additional outputs:
- short rationale for `possibly inaccurate` or worse
- boolean `accept_for_writeback`
- optionally normalized risk categories such as `low`, `medium`, `high`

### B. Deck factual audit mode

Purpose:
Evaluate the original card itself for probable factual problems.

Important distinction:
A card can be semantically faithful as a rewrite target but still be medically or factually wrong. That is why deck audit must be a separate function.

### Deck audit output should include
- overall score
- concise rationale when suspicious
- optional category tags such as:
  - ambiguity
  - likely outdated
  - threshold mismatch
  - incomplete answer
  - contradiction
  - low confidence factual claim

### Best practice

Run validation prompts with lower temperature than rewrite prompts.

---

## Randomization at Review Time

### Core requirement

Each review should show one precomputed prompt variant chosen at random, while preserving the same variant between front and back.

### Recommended mechanism

1. Card template reads `AIRewriteData`.
2. It determines which field is the active prompt field for this card template.
3. It selects one variant index.
4. It persists that selection under a stable key for the current card render.
5. Front shows the selected prompt variant.
6. Back retrieves the same selected variant and shows the corresponding prompt text plus the answer.

### Why not use independent random selection on both sides?

Because the user could see one phrasing on the front and a different one echoed on the back, which is confusing and can be incorrect.

### Portability recommendation

Plan around a persistence pattern that is known to work better than plain global variables. Mobile behavior matters here.

### Fallback behavior

If persistence is unavailable on a specific preview surface:
- default to original prompt
- or use a deterministic fallback variant
- and clearly mark the preview mode limitation in documentation

---

## Template Patching Strategy

This deserves special care.

### Goals
- avoid breaking existing formatting
- make insertion idempotent
- allow rollback
- work across front/back templates
- support multiple note types

### Recommended approach

For each supported note type, maintain a patch recipe:
- fields to add
- template markers/scripts to inject
- CSS additions if needed
- rollback instructions

### Template patch design principles

1. **Namespace everything**: ids, classes, script functions, and markers should be clearly app-owned.
2. **Be idempotent**: re-running patching should not duplicate injected code.
3. **Store patch version**: both in app DB and in template comments.
4. **Support rollback**: user should be able to restore original templates.
5. **Prefer minimal invasiveness**: do not reformat unrelated HTML.

### Human approval checkpoint

Before patching a note type for the first time, show:
- original template diff
- proposed template diff
- fields to be added
- impact summary

---

## Review and Approval UX

### Rewrite workflow UI

Recommended flow:
1. Select deck / query.
2. App scans note types and support status.
3. User reviews which note types will be patched or cloned.
4. User chooses variant count and distribution.
5. User selects provider/model.
6. Job runs.
7. User reviews results by note, batch, or risk level.
8. User approves writeback or regenerates flagged variants.

### Audit workflow UI

Recommended flow:
1. Select deck / query.
2. Choose audit-only mode.
3. Run scoring.
4. Filter by score threshold.
5. Inspect concise rationales.
6. Export flagged set.

### Useful filters
- unsupported cards
- validation failures
- `possibly inaccurate` or worse
- by note type
- by template
- by tag/deck
- by provider run

---

## Suggested Backend Modules

### 1. `anki_client`
Responsibilities:
- AnkiConnect transport
- find notes
- fetch note info
- fetch model field names
- fetch fields used on templates
- update note fields

### 2. `note_type_registry`
Responsibilities:
- known note-type handlers
- support classification
- clone-vs-patch decision logic

### 3. `card_interpreter`
Responsibilities:
- map note + template to active prompt side
- derive rewrite target
- build intermediate representation

### 4. `content_normalizer`
Responsibilities:
- HTML stripping for LLM view
- protected token extraction
- cloze span preservation
- media placeholder preservation

### 5. `llm_provider`
Responsibilities:
- provider abstraction
- OpenAI-compatible endpoints
- Google provider support
- retries, backoff, timeouts
- structured output handling

### 6. `rewrite_engine`
Responsibilities:
- construct prompts
- fan out requested number of variants
- enforce distribution logic
- collect candidate outputs

### 7. `validation_engine`
Responsibilities:
- variant fidelity validation
- deck audit mode
- structured rating outputs

### 8. `template_patch_manager`
Responsibilities:
- clone note types if needed
- add app-owned fields
- patch templates
- rollback patches

### 9. `storage`
Responsibilities:
- SQLite models
- job state
- logs
- cached prompt/output pairs

### 10. `jobs`
Responsibilities:
- async work queue
- resumable jobs
- progress tracking
- cancellation

### 11. `api`
Responsibilities:
- REST endpoints
- auth/session if needed locally
- job control

---

## Suggested Frontend Structure

### Main screens

#### 1. Dashboard
- collection connection status
- provider status
- recent jobs
- note-type support summary

#### 2. Deck / Query Browser
- list decks
- query builder
- show note-type composition
- show estimated work volume

#### 3. Rewrite Configuration
- variant count
- distribution sliders/inputs
- provider/model settings
- validation on/off
- approval mode

#### 4. Template Compatibility Screen
- supported note types
- caution flags
- clone/patch options
- diff preview

#### 5. Rewrite Review Screen
- original prompt
- answer
- generated variants
- validation scores
- regenerate / approve / reject actions

#### 6. Audit Dashboard
- suspicious cards
- filter by rating
- rationale snippets
- export results

#### 7. Settings
- provider profiles
- endpoint URLs
- API keys
- rate limits
- default prompt sets

---

## LLM Provider Support

The provider abstraction should support at least these modes:

### 1. OpenAI API
Standard hosted API key flow.

### 2. OpenAI-compatible local/server endpoint
Examples include local inference servers that expose a `/v1`-style interface.

### 3. Google API
Separate adapter with provider-specific request handling.

### Provider profile fields
- provider kind
- model name
- base URL
- API key
- temperature
- max tokens
- timeout
- concurrency cap
- optional JSON mode / structured output settings

### Strong recommendation

Support **provider profiles** rather than one global provider config. Users may want different providers for:
- rewrite generation
- fidelity validation
- factual audit

---

## Prompting Strategy

### Prompt families to maintain separately

1. rewrite-conservative
2. rewrite-moderate
3. rewrite-aggressive
4. validate-semantic-fidelity
5. audit-card-accuracy
6. classify-support-risk (optional helper prompt if ever used)

### Prompt output format

Require strict structured output.

For example, rewrite outputs should include:
- variant id
- rewrite style
- rewritten text
- warnings if any

Validation outputs should include:
- rating
- rationale
- concerns
- accept boolean

### Prompt versioning

Store prompt template version with every generation run so later debugging is possible.

---

## Testing Plan

### Unit tests

#### Card/template interpretation
- Basic note types map to correct prompt field
- reversed note types map to correct prompt field per template
- cloze types correctly identify rewriteable context
- unsupported types are labeled correctly

#### Content normalization
- HTML stripped safely for model input
- line breaks preserved where meaningful
- media references preserved or masked
- cloze spans extracted and reinserted losslessly

#### Rewrite post-processing
- structured output parsing
- invalid JSON fallback handling
- delimiter escaping
- variant deduplication

#### Validation parsing
- valid ratings accepted
- unknown ratings rejected
- rationale requirement enforced for low-confidence scores

#### Distribution logic
- variant count mapped correctly across conservative/moderate/aggressive
- user overrides handled correctly

### Integration tests

#### Anki round-trip
- find notes → fetch note info → update app fields → verify persistence

#### Template patching
- cloned note type contains required fields
- patch is idempotent
- rollback restores prior state

#### Render behavior
- front side shows one selected variant
- back side shows the same selected variant
- fallback behavior works when persistence is unavailable

#### Provider adapters
- OpenAI profile works
- OpenAI-compatible local endpoint works
- Google profile works
- provider-specific errors are surfaced clearly

### End-to-end tests

- generate variants for a small Basic deck
- generate variants for a Basic-and-reversed deck
- run audit-only mode on a deck
- reject/approve flagged variants
- re-run generation after note edits

### Property-based / fuzz-style tests

High value for:
- malformed HTML
- odd Unicode
- empty fields
- nested markup
- malformed cloze strings
- very large notes

---

## Validation and QA Cases to Include

1. Card with bold/italic/HTML line breaks.
2. Card with embedded images or audio tags.
3. Card with multiple cloze deletions in one sentence.
4. Card with nested or overlapping cloze-like patterns.
5. Reverse cards where `Back` is the active prompt.
6. Cards with tables or lists.
7. Cards with `type:` answers in template.
8. Cards whose fields are mostly custom HTML wrappers.
9. Mobile rendering cases.
10. Preview mode vs real review mode behavior.

---

## Major Failure Modes and What to Watch For

### 1. Semantic drift
Aggressive rewrites may subtly alter what the card is testing.

Mitigations:
- answer-aware prompt
- fidelity validation by default
- review UI for borderline cases

### 2. Cloze corruption
If a cloze token is damaged, the card becomes broken.

Mitigations:
- protect cloze spans before generation
- rewrite context only
- exact reinsert step
- dedicated cloze tests

### 3. Front/back mismatch of selected variant
This is one of the most important technical risks.

Mitigations:
- persistent selection strategy
- integration tests across platforms
- fallback path

### 4. Template breakage
Existing custom templates may already contain fragile JS/CSS.

Mitigations:
- clone note types rather than mutate in place
- preview diff
- rollback support
- support classification

### 5. Field-size and encoding issues
Large JSON blobs in fields can become awkward.

Mitigations:
- compact JSON schema
- compression only if truly needed
- trim metadata stored in-field
- keep operational logs in app DB instead

### 6. Provider unreliability or latency
Large decks can stress APIs.

Mitigations:
- job queue
- retry/backoff
- caching by content hash + prompt version + model profile
- resumable runs

### 7. Deck content changing after generation
If the source card changes, variants may become stale.

Mitigations:
- hash original prompt/answer
- mark rewrites stale when source changes
- surface “needs regeneration” state

### 8. User trust erosion from over-automation
Users need confidence that the app is not silently damaging their deck.

Mitigations:
- explicit previews
- validation rationale
- diff visibility
- rollback tools
- audit trail

### 9. Cross-platform JS inconsistencies
Desktop, AnkiWeb, AnkiMobile, and AnkiDroid do not always behave identically.

Mitigations:
- documented compatibility targets
- persistence-based approach
- platform-specific tests

### 10. Custom note-type ambiguity
Some templates are too custom to infer safely.

Mitigations:
- classify as unsupported/caution
- audit-only fallback
- optional advanced manual mapping UI later

---

## Security and Privacy Considerations

### Sensitive data risk
Decks may contain proprietary or personal information.

Recommended controls:
- clear warning before sending note content to remote APIs
- support local LLM endpoints
- provider profiles with explicit labels like “local only” or “hosted API”
- optional field redaction rules before sending content externally

### API key handling
- store encrypted at rest if persisted
- avoid exposing secrets to frontend beyond necessity
- prefer backend-mediated provider calls

### Logging
- do not log raw card content by default unless user opts in for debugging
- redact keys and sensitive text in error logs

---

## Observability and Debugging

Useful telemetry/logging:
- note id
- model name
- template name
- prompt version
- provider profile
- latency
- validation score
- whether writeback succeeded
- whether template patch version matched expectation

Helpful debug features:
- inspect generated prompt
- inspect provider raw response
- inspect parsed rewrite output
- inspect current template patch version

---

## Rollback and Recovery Plan

This project should have a strong rollback story from day one.

### User-visible rollback functions
- restore original note type templates
- remove app-owned fields from cloned note types if desired
- discard generated variants for selected deck/query
- restore previous rewrite data version

### Internal rollback data to store
- original template HTML/CSS snapshot
- original note type field list
- patch version
- timestamp and operator

---

## Ordered Implementation Timeline

### Phase 1: Project foundations
- set up backend and frontend shells
- add SQLite app DB
- add provider profile model
- add basic Anki connection test

### Phase 2: Anki introspection
- fetch decks and notes
- fetch note types and fields
- discover fields used on templates
- build support classification logic

### Phase 3: Card understanding engine
- map template → active prompt field
- implement content normalization
- implement cloze token protection
- define structured intermediate representation

### Phase 4: LLM provider abstraction
- add OpenAI support
- add OpenAI-compatible endpoint support
- add Google support
- add retries/timeouts/structured output handling

### Phase 5: Rewrite engine
- implement rewrite prompt families
- implement distribution logic
- generate candidate variants
- add deduplication and formatting cleanup

### Phase 6: Validation engine
- implement semantic fidelity validation
- implement deck audit prompt and scoring
- add filtering and structured results

### Phase 7: Template patch manager
- implement app-owned field strategy
- implement clone note type workflow
- implement patch diff preview
- implement rollback support

### Phase 8: Review-time randomization
- inject template logic
- persist selected variant across front/back
- add fallback behavior
- test on multiple review surfaces

### Phase 9: Review UI and audit UI
- add rewrite preview/approval screen
- add audit dashboard
- add filtering/export
- add job progress UI

### Phase 10: Hardening and scale
- caching
- resumable jobs
- stale rewrite detection
- better unsupported-type handling
- broader compatibility testing

---

## Features Worth Deferring Until After MVP

1. Manual field-to-template mapping UI for exotic note types.
2. Automatic adaptation based on user performance (“harder rewrites after Easy”).
3. Variant quality scoring from actual review behavior.
4. Collaborative/shared prompt packs.
5. Bulk publishing/export of app-managed note type presets.
6. Multi-model comparison for the same deck.

---

## Final Build Recommendations

If I were building this, I would make these non-negotiable:

1. **Do not create duplicate cards.**
2. **Do not patch user templates silently.**
3. **Clone note types when patching risk is nontrivial.**
4. **Use compact JSON app fields instead of many variant fields.**
5. **Treat reversed-card prompt fields correctly.**
6. **Treat cloze content as protected structure.**
7. **Use default-on validation for generated variants.**
8. **Keep deck audit mode separate from variant validation.**
9. **Make rollback first-class.**
10. **Test front/back persistence on mobile before claiming full compatibility.**

This gives the project a much better chance of being reliable, maintainable, and trustworthy for serious study use.
