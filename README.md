# Prospector

An agentic lead-prospecting system built for the Techvruk "AI Agentic System Challenge".

Give it a goal in plain English -- *"Find 30 dental clinics in Pune that would buy an
AI phone receptionist"* -- and it plans, acts through real tools (OpenStreetMap,
business websites), observes what happened, re-plans when a step fails or comes up
short, and returns a ranked, reasoned lead list. The differentiator: it **gets better
with use**. You mark leads good/bad, it reflects on what it got wrong, proposes new
scoring rules, validates each one on data it never trained on, and keeps only the
rules that measurably improve accuracy.

No agent framework (no LangChain, no CrewAI). The loop, the tool registry, and the
learning validator are hand-written so the agentic pattern is visible in the code,
not hidden behind a library.

## Problem

Cold outreach for a local-business product (an AI phone receptionist) starts with a
list: who to call, and why they'd care. Building that list by hand is slow. A
plain LLM call that "generates 30 leads" hallucinates businesses that don't exist.
Prospector instead treats lead generation as an **agentic task**: a goal decomposes
into a plan, the plan executes through tools that touch real data (OpenStreetMap for
business listings, live HTTP fetches for each business's website), and every claim
in the final report traces back to something actually observed.

## Why this is agentic, not just a script

| Pattern | Where it lives |
|---|---|
| **Plan** | `Agent.run()` step 1: one LLM call turns the goal into `{place, niches, target_count, plan}` (`prospector/agent.py`) |
| **Act** | A tool registry (`geocode`, `search_businesses`, `widen_area`, `enrich`, `score`, `deep_research`, `write_hooks`, `finish`) the LLM calls one at a time |
| **Observe** | Every tool call returns a plain-text observation, truncated and fed back into the next LLM turn |
| **Re-plan (ReAct)** | A failure or a low result count is *never* a crash -- it's an observation the LLM reasons over and reacts to (e.g. calling `widen_area` after too few results) |
| **State** | `RunState` persists to `runs/<run_id>/state.json` after every single step, plus an append-only `trace.jsonl` |
| **Respond** | `finish` writes a final answer; `report.py` renders the full trace into `report.md` |

## Architecture

```mermaid
flowchart TD
    UI["Next.js UI"] -->|"POST /api/runs, GET /api/runs/:id, POST /api/labels, POST /api/learn"| API["FastAPI: server.py"]
    API -->|"background thread"| G["Goal text"]
    G --> P["PLAN: one LLM call"]
    P --> S["RunState: place, niches, target_count, plan"]
    S --> L{"Loop until finish or max_steps"}
    L --> T["LLM: thought + action + args"]
    T --> X["Execute tool"]
    X --> O["Observation"]
    O -->|"persist state.json + trace.jsonl"| L
    O -->|"failure or low results"| T
    L -->|"finish"| F["report.md + leads.csv"]
    API --> MEM["Memory: rules, labels, history"]
    API --> LRN["Learner: learn"]
```

Tools touch three real data sources:
- **OSM Nominatim** -- geocode a place name to a bounding box (1 req/s, polite User-Agent)
- **OSM Overpass** -- business search by tag (dentist, lawyer, vet, ...), multiple
  mirror endpoints with retry/backoff
- **Business websites** -- direct HTTP fetch (+ a couple of common subpages) to detect
  email, phone, online booking, chat widgets, and contact forms

## The learning loop (the differentiator)

```mermaid
flowchart LR
    U["User marks lead good/bad"] --> M["Memory: labels.jsonl"]
    M --> SP["Deterministic 3-way split<br/>by sha1(lead_id) % 5:<br/>0=test 1=select rest=train"]
    SP --> TR["Train: find leads the<br/>current rules mis-score"]
    TR --> LLM["ONE LLM call: propose up to<br/>5 candidate rules from misses<br/>+ feature catalogue"]
    LLM --> V["Validate: object shape,<br/>feature exists, op matches type,<br/>weight numeric + in range"]
    V --> H["Score each candidate ALONE<br/>on the SELECT split"]
    H -->|"gain > 0 AND train acc<br/>drop at most 2 pts"| KEEP["Keep, add greedily,<br/>re-check against growing set"]
    H -->|"else"| REJ["Reject + log reason"]
    KEEP --> RM["Try removing each old rule<br/>on SELECT; drop if it doesn't<br/>hurt -- or must strictly help<br/>when select has fewer than 10 labels"]
    RM --> REP["Report acc + p@k on<br/>TEST only, never select"]
    REP --> HIST["history.jsonl: acc_before/after,<br/>p@k before/after"]
```

The LLM proposing rules **never sees select or test data** -- only misclassified
training leads. A unit test (`tests/test_learner.py`) inspects the exact prompt text
sent to the LLM and asserts no select/test lead id appears in it.

Rules are chosen on the **select** split and graded on the **test** split, which are
disjoint. Choosing and grading on the same data would make every accuracy number
optimistic (a rule that merely overfits the validation set would still look like a
win). When there isn't enough labeled data for a clean 3-way split (each of select
and test needs at least 3 labels with both classes present), `learn()` falls back to
select and test sharing the same records and marks the history entry
`"note": "optimistic: selection and test share data"` so that's visible, not hidden.
If even the combined set is too small, `learn()` refuses to touch memory at all and
reports why instead of guessing. `p@k` uses `k = min(10, n_test // 2)` and is reported
as unavailable when the test set has fewer than 4 labels, rather than a misleading
number computed over 1-2 points.

## Honesty rules

- A `Lead` field that hasn't been observed stays `None`/`""`/`[]` -- never guessed.
- LLM output only ever lands in `Lead.research`, `Lead.reasons`, and `Lead.hook`, and
  `write_hooks` is explicitly instructed to use *only* facts already on the lead.
- Scoring rules only ever reference `features.py` output (a small, typed, documented
  catalogue) -- never raw fields directly -- so every rule is auditable.
- A learned rule is kept only if it improves **select-split** accuracy without
  dropping train accuracy by more than 2 points. Nothing is kept because it "sounds
  right," and nothing is graded on the same data used to pick it (see below).
- `has_booking`/`chat_widget`/`has_contact_form` are only ever set from a page that
  actually returned HTTP 200. A 403/404 error page is never scanned, so it can never
  produce a false "no booking found" -- those fields stay `None`/unknown instead.
  `chat_known` (a feature) is true only when the site was actually fetched
  successfully, and the `no_chat_widget` scoring bonus only applies when
  `chat_known` is true -- a lead that was never enriched gets no credit for an
  absence it was never actually checked for.

## Live AI receptionist calls

Every lead is a business Prospector thinks would benefit from an AI phone
receptionist -- so the top leads on a run get a live, callable demo of exactly
that, in the browser.

- After `write_hooks`, the agent can call `prepare_receptionists` to have the
  LLM write a persona system instruction for up to 3 top leads, using *only*
  observed facts (business name, niche, address, observed opening hours) --
  the same honesty invariant as `write_hooks`: no invented staff names,
  prices, services, or phone numbers. Any question it can't answer from the
  facts gets "a staff member will call you back", with an offer to take a
  message. If a lead never went through that tool, `/live-session` builds the
  same persona deterministically from the same template at request time.
- Clicking **"Call its AI receptionist"** (on the run page's top lead cards,
  or in the review detail panel) opens a call panel that connects to the
  [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) with that
  persona. **The real `GEMINI_API_KEY` never reaches the browser.** The
  server (`prospector/live.py`) mints a short-lived (30 min), single-use
  ephemeral token whose `live_connect_constraints` lock it to one model and
  one fully-formed session config (the persona, the voice, the tool
  declarations) -- the browser can connect with it, but can't repurpose it for
  a different model or a different business's persona.
- Mic audio is downsampled to 16-bit PCM at 16kHz in an inline AudioWorklet
  and streamed to the Live API; output audio (PCM16 at 24kHz) is scheduled
  gaplessly for playback and stops immediately on a `serverContent.interrupted`
  (barge-in). Live captions show both sides of the conversation as they
  transcribe. If the model calls its one tool, `take_message`, the panel POSTs
  it to `/api/runs/{run_id}/leads/{lead_id}/messages`, shows a "message taken"
  card, and reports the tool result back to the model.
- Disclosure: this uses `gemini-3.8-live` (a preview model, overridable via
  `GEMINI_LIVE_MODEL`), on the free tier. It's a browser-audio demo of the
  receptionist persona, not a production telephony integration -- there's no
  real phone number and no PSTN involved.

## Feature catalogue

`prospector/features.py` computes ~20 deterministic, side-effect-free features from a
`Lead`: `has_website`, `site_ok`, `chat_known`, `fetch_ok`, `has_email`, `email_count`,
`has_phone`, `has_booking`, `booking_known`, `has_chat_widget`, `chat_vendor`,
`chat_incumbent`, `has_contact_form`, `hours_known`, `open_24_7`, `open_weekends`,
`address_known`, `niche`, `high_ticket_niche`, `research_has_text`,
`research_mentions_phone_only`. These are the *only* inputs learned rules may
reference.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY
uvicorn server:app --port 8000
```

In another terminal:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. (Or run `.\dev.ps1` from the repo root to start both at once.)

Or via the CLI:

```bash
python cli.py run "Find 30 dental clinics in Pune that would buy an AI phone receptionist"
python cli.py label <run_id>   # mark leads good/bad
python cli.py learn            # propose + validate new rules from labels
```

## Tests

Backend (pytest -- no network access, no real LLM calls; every test injects a
scripted LLM and/or monkeypatches OSM/website calls):

```bash
pip install -r requirements.txt
python -m pytest
```

Frontend end-to-end (Playwright, chromium only, fully offline):

```bash
cd web
npm install
npx playwright install chromium   # first time only
npm run test:e2e
```

`test:e2e` starts its own scripted FastAPI backend (`tests/e2e_server.py`, port
8010 -- a deterministic stand-in LLM plus monkeypatched OSM/website tools, zero
network access, zero Gemini calls) and a dedicated Next dev server (port 3010),
both separate from the demo's normal 8000/3000 ports so it's safe to run
alongside `dev.ps1`. It drives the full run -> review -> learn -> live-call
flow through the real FastAPI routes and the real agent loop, and writes
1440x900 screenshots of each page to `docs/screenshots/`.

## Screenshots

All captured from the scripted end-to-end suite (`npm run test:e2e`), not a
live Gemini run -- see [Tests](#tests) above.

| Run (in progress) | Run (done) |
|---|---|
| ![Run in progress](docs/screenshots/run.png) | ![Run done](docs/screenshots/run-done.png) |

| Review | Learn |
|---|---|
| ![Review](docs/screenshots/review.png) | ![Learn](docs/screenshots/learn.png) |

| Runs history | Live AI receptionist call |
|---|---|
| ![Runs](docs/screenshots/runs.png) | ![Call panel](docs/screenshots/call.png) |

## Sample input/output

<!-- TODO: fill in with a real run's output before submission. Do not fabricate
     numbers here -- paste the actual report.md / leads.csv excerpt from a live run
     once GEMINI_API_KEY is configured and a full run has completed. -->

## Data and legal notes

- Map data (c) OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).
- Nominatim usage policy: max 1 request/second, real `User-Agent` with a contact
  email (`ganeshpatil643613@gmail.com`) -- both are enforced in `prospector/osm.py`.
- Overpass API: multiple public mirrors are tried in order with retry/backoff, since
  any single mirror can be slow or rate-limited.
- Website enrichment fetches only publicly served pages with a normal browser
  User-Agent; it never bypasses auth, paywalls, or robots directives-backed blocks.

## AI tools used

Claude Code was used as a coding assistant to help write this implementation from a
hand-authored design contract. The architecture, the agentic loop design, the
learning/validation algorithm, and all product decisions are the author's; the
assistant implemented them under direction and review.

## Limitations

- OSM coverage is uneven outside major metros; some real businesses simply aren't
  tagged and won't be found no matter how much the area is widened.
- Website enrichment is a plain HTTP fetch with BeautifulSoup -- JS-rendered sites
  (no server-side HTML) will show as `fetch_error`/no signals even if they have a
  chat widget or booking flow.
- The learning loop needs at least 12 labels with both classes present before it will
  propose anything; early on, scoring is just the fixed base heuristic.
- Holdout accuracy is measured on whatever the user has labeled so far, which is
  small and non-random (it's whichever leads the user reviewed) -- treat the accuracy
  chart as a trend indicator across runs, not a rigorous ML benchmark.
- `write_hooks` and `deep_research` cost an extra LLM/HTTP call per lead, so the
  agent only runs them on a capped top-N subset, not every lead found.
