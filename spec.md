# spec.md — Phase 1 Implementation Spec (Discord-free Core + SQLite + GLM4.7)

**Audience:** Claude Code (autonomous coding agent)
**Language:** English
**Scope:** Phase 1 only — implement and validate the offline pipeline that ingests message fixtures, stores them in SQLite, generates daily summaries + deltas using **Z.ai GLM4.7**, and provides CLI commands to run/preview results **without Discord**.

You MUST implement and run tests yourself (as if you are a human tester), including:
- unit tests
- integration tests
- end-to-end runs that generate artifacts for multiple days and validate delta behavior

The goal is to finish Phase 1 with high confidence before attaching Discord in Phase 2.

---

## 0. What Phase 1 Must Deliver

### 0.1 Core capabilities
1) Persist messages into SQLite (from fixture files and/or generated synthetic data)
2) Generate **Daily Channel State** (structured JSON) from messages for a given date window
3) Generate **Daily Channel Summary** (human-readable Markdown)
4) Generate **Daily Channel Delta** comparing today vs. previous day (JSON diff + Markdown)
5) Generate a **Global Digest** (rollup across channels)
6) Provide a CLI to run all of the above for:
   - a specific date (`--date YYYY-MM-DD`)
   - a date range (`--start YYYY-MM-DD --end YYYY-MM-DD`)
   - a rolling pseudo-window (`--last-hours N`)
7) Provide a dry-run mode that prints outputs and also writes them to SQLite for later comparison.

### 0.2 Constraints / Assumptions
- Data store: **SQLite** (required)
- Real LLM calls: **Z.ai GLM4.7**
- API key available as environment variable: `GLM_API_KEY` (already exported in `~/.zshrc`)
- Phase 1 is **Discord-free**: no Discord SDK, no gateway events.

---

## 1. Recommended Tech Choices (you choose, but be consistent)

Pick one stack and implement everything in it:
- **Python 3.11+** (recommended for quick CLI + testing), OR
- Node.js 20+ (acceptable)

**If you choose Python, preferred libraries:**
- `argparse` or `typer` (CLI)
- `pydantic` (schemas)
- `sqlite3` (pure Python, no ORM required)
- `pytest` with `pytest-asyncio` (testing)
- `rich` (beautiful terminal output - **STRONGLY RECOMMENDED**)
- `python-dotenv` (optional; but key is already in env)

If you choose Node:
- `commander` or `yargs` (CLI)
- `zod` (schemas)
- `better-sqlite3` or `sqlite3`
- `vitest` or `jest`

Do NOT add Discord dependencies in Phase 1.

---

## 2. Repository Layout (required)

Use this directory structure:

```
project-root/
  README.md
  pyproject.toml (or package.json)
  src/
    app/
      __init__.py
      cli.py
    core/
      __init__.py
      models.py
      timewindow.py
      summarizer.py
      delta.py
      digest.py
      renderer.py
      events.py          # Event-driven architecture
    infra/
      __init__.py
      db.py
      glm_client.py
      fixtures.py
  fixtures/
    sample_3days.jsonl
    sample_minimal.jsonl
  tests/
    conftest.py
    test_db.py
    test_timewindow.py
    test_delta.py
    test_events.py      # Event system tests
    test_summarizer_mock.py
    test_e2e_offline.py
  data/
    app.db (created at runtime)
```

(If Node, mirror the same conceptual layout.)

---

## 3. Data Model

### 3.1 MessageEvent (input record)
Represent each message as a normalized record:

Fields (minimum):
- `message_id`: string (unique within DB; in fixtures may be synthetic)
- `channel_id`: string
- `channel_name`: string
- `author_id`: string
- `author_name`: string
- `created_at`: ISO8601 string with timezone OR naive local time + explicit `timezone`
- `content`: string (may be empty)
- `attachments`: list of `{url, filename, content_type}` (optional)
- `links`: list of urls extracted from content (optional)
- `reply_to_message_id`: string | null (optional)

### 3.2 DailyChannelState (structured JSON produced by LLM)
This MUST be stable because deltas depend on it.

Schema (required keys, empty arrays allowed):
```json
{
  "channel_name": "alice",
  "date": "2026-01-17",
  "topics": ["..."],
  "progress": {
    "started": ["..."],
    "continued": ["..."],
    "finished": ["..."],
    "blocked": ["..."]
  },
  "artifacts": {
    "links": ["..."],
    "repos": ["..."],
    "docs": ["..."]
  },
  "questions": ["..."],
  "help_requests": ["..."],
  "next_steps": ["..."]
}
```

### 3.3 DailyChannelDelta (structured JSON)
Derived via JSON-to-JSON comparison (NOT message-to-message diff).

Schema:
```json
{
  "channel_name": "alice",
  "date": "2026-01-17",
  "compared_to": "2026-01-16",
  "new_topics": ["..."],
  "resolved_topics": ["..."],
  "progress_changes": {
    "started_now": ["..."],
    "finished_now": ["..."],
    "new_blockers": ["..."],
    "resolved_blockers": ["..."]
  },
  "new_links": ["..."],
  "new_help_requests": ["..."]
}
```

### 3.4 GlobalDigest
A Markdown text (and optionally a small JSON) that rolls up:
- Top highlights across channels (top 5)
- Help requests across channels (top 5)
- New links across channels (top 10)

---

## 4. SQLite Schema (required)

Create a migration (even if simple) that builds these tables:

### 4.1 messages
- `message_id` TEXT PRIMARY KEY
- `channel_id` TEXT NOT NULL
- `channel_name` TEXT NOT NULL
- `author_id` TEXT NOT NULL
- `author_name` TEXT NOT NULL
- `created_at` TEXT NOT NULL  (ISO8601)
- `content` TEXT NOT NULL
- `attachments_json` TEXT NOT NULL DEFAULT '[]'
- `links_json` TEXT NOT NULL DEFAULT '[]'

Indexes:
- `(channel_id, created_at)`
- `(channel_name, created_at)`

### 4.2 daily_channel_state
- `date` TEXT NOT NULL
- `channel_id` TEXT NOT NULL
- `channel_name` TEXT NOT NULL
- `state_json` TEXT NOT NULL
- `summary_md` TEXT NOT NULL
- `created_at` TEXT NOT NULL

PRIMARY KEY `(date, channel_id)`

### 4.3 daily_channel_delta
- `date` TEXT NOT NULL
- `channel_id` TEXT NOT NULL
- `channel_name` TEXT NOT NULL
- `compared_to` TEXT NOT NULL
- `delta_json` TEXT NOT NULL
- `delta_md` TEXT NOT NULL
- `created_at` TEXT NOT NULL

PRIMARY KEY `(date, channel_id)`

### 4.4 global_digest
- `date` TEXT PRIMARY KEY
- `digest_md` TEXT NOT NULL
- `created_at` TEXT NOT NULL

---

## 5. Time Window Rules (Asia/Seoul)

Default timezone: `Asia/Seoul`

Support three modes:

### 5.1 Date mode
Input: `--date YYYY-MM-DD`
Window: `[YYYY-MM-DD 00:00:00, YYYY-MM-DD 23:59:59]` in KST.

### 5.2 Range mode
Input: `--start YYYY-MM-DD --end YYYY-MM-DD` (inclusive)
Run date mode for each day sequentially.

### 5.3 Pseudo-day mode (rolling)
Input: `--last-hours N`
Window: `[now - N hours, now]` in KST.
In this mode, set the "effective date" label to `now`'s date, and store outputs under that date.

---

## 6. GLM4.7 Integration (real calls)

### 6.1 Env
- Read API key from environment variable `GLM_API_KEY`
- If missing, fail fast with a clear error.

### 6.2 Client
Implement a minimal client wrapper:
- `glm_client.chat(messages, model="glm-4.7", temperature=0.2, max_tokens=...) -> text`
- Retries: at least 2 retries with exponential backoff for transient errors
- Logging: log request id / timing (do not log full user content in verbose unless debug flag is set)

> If Z.ai provides an OpenAI-compatible API, implement it as such; otherwise implement the native REST call.
> You are responsible for reading the correct endpoint format and implementing it correctly.

### 6.3 Prompting (must be deterministic-ish)
Use low temperature (0.0–0.2).
Require JSON output for `DailyChannelState` and `DailyChannelDelta`.

---

## 7. Summarization Pipeline

### 7.1 Pre-processing
For each channel:
- load messages in the time window
- normalize whitespace
- extract links from content (regex)
- represent each message in a compact format:
  - `[HH:MM] author: content (links...) (attachments...)`

### 7.2 Chunking
If too many messages / too long:
- chunk by message count (e.g., 50 per chunk) or by token estimate
- run LLM "condense" step per chunk into short bullets
- then feed condensed bullets into the final "state JSON" step

### 7.3 Produce DailyChannelState JSON (LLM)
Prompt requirements:
- Must output VALID JSON matching schema
- Must be faithful to messages (no hallucinated claims)
- Use empty arrays rather than omitting keys
- Extract repos/docs/links when present
- Identify blockers, questions, help requests if any

### 7.4 Render Summary Markdown
Convert state_json into Markdown:
- Title line: `## #channel-name — Daily Summary (YYYY-MM-DD)`
- Sections:
  - Highlights (3–6 bullets; derive from progress/topics)
  - Blockers (if any)
  - Help Requests (if any)
  - Links (top N)
  - Next Steps (if any)

### 7.5 Delta computation (JSON diff)
Implement delta generation primarily by code (not by LLM), using simple set differences:
- new_topics = today.topics - yesterday.topics
- resolved_topics = yesterday.topics - today.topics (optional)
- finished_now = today.progress.finished - yesterday.progress.finished
- started_now = today.progress.started - yesterday.progress.started
- new_blockers = today.progress.blocked - yesterday.progress.blocked
- resolved_blockers = yesterday.progress.blocked - today.progress.blocked
- new_links = today.artifacts.links - yesterday.artifacts.links
- new_help_requests = today.help_requests - yesterday.help_requests

If yesterday state does not exist:
- create delta with `compared_to = null` behavior:
  - delta_md should say "No previous day data available."

### 7.6 Delta Markdown
- `### Delta vs. YYYY-MM-DD`
- Bullets for:
  - New topics
  - Finished items
  - New blockers
  - New links
  - New help requests

### 7.7 Global Digest
Aggregate all channels' summaries/deltas:
- top highlights: choose 1–2 per channel (prefer finished/new blockers/help requests)
- help requests: all combined, sorted by count
- links: dedupe and cap

Render:
- `# Daily Digest (YYYY-MM-DD)`
- `## Top Highlights`
- `## Help Requests`
- `## New Links`
- `## Per-Channel Summaries` (optional in Phase 1; OK to include)

Store into `global_digest` table.

---

## 8. CLI Spec (required)

Entry point: `python -m app.cli ...` (or `app` command)

### 8.1 CLI Output Requirements (CRITICAL)

The CLI MUST provide beautiful, rich terminal output using the `rich` library (or equivalent):

**PROVEN IN v05**: Beautiful CLI output was a major factor in achieving 9.7/10 score. The `rich` library transformed the user experience from basic to professional.

**Required output elements:**
- **Progress bars**: Show progress for long-running operations (ingest, run commands)
- **Tables**: Display structured data like:
  - Ingest summary (messages per channel)
  - Test results
  - Message previews
- **Panels**: Highlight important information like:
  - Channel summaries
  - Delta information
  - Self-test results
- **Colored output**: Use color to differentiate:
  - Success messages (green)
  - Errors (red)
  - Warnings (yellow)
  - Information (cyan/blue)
- **Status indicators**: Use checkmarks, X marks, and other symbols

**Example output patterns:**
- Ingest command: Progress bar + summary table
- Run command: Progress bar + highlights/links tables
- Preview command: Message table + state panel
- Selftest: Panel with pass/fail summary

**PROVEN PATTERN FROM v05**:
```python
# Progress bars for long operations
with Progress() as progress:
    task = progress.add_task("[green]Ingesting messages...", total=len(messages))
    db.insert_messages(messages)
    progress.update(task, completed=len(messages))

# Tables for structured data
table = Table(title="Ingest Summary", show_header=True, header_style="bold magenta")
table.add_column("Channel", style="cyan")
table.add_column("Messages", justify="right", style="green")

# Panels for highlighted info
panel = Panel(md, title=f"[bold blue]#{channel_name}[/bold blue]", border_style="blue")
```

### 8.2 Commands

#### `ingest`
Ingest fixtures into SQLite.

Options:
- `--db data/app.db`
- `--fixture fixtures/sample_3days.jsonl`
- `--append/--reset` (reset drops/recreates tables)

#### `run`
Run summarization + delta + digest.

Options (mutually exclusive window selection):
- `--date YYYY-MM-DD`
- `--start YYYY-MM-DD --end YYYY-MM-DD`
- `--last-hours N`

Other options:
- `--db data/app.db`
- `--dry-run` (do not store outputs; still print)
- `--store` (store outputs; default true)
- `--channels channelA,channelB` (optional filter)
- `--debug` (more logs)
- `--mock` (use mock LLM responses)

Output:
- prints channel summaries + deltas to stdout (with rich formatting)
- prints global digest (with rich formatting)

#### `preview`
Preview one channel for one date/window.

Options:
- same window options as `run`
- `--channel-name alice`

#### `selftest`
A special command that:
- creates a temporary DB (isolated from real data)
- ingests fixtures
- runs `run` across a 3-day range
- validates that:
  - states exist for each day/channel
  - deltas exist for day 2+ and contain expected "new" items (based on the fixture's known content)
  - digest rolls up highlights across channels
- displays results in a rich table with PASS/FAIL indicators
- exits with non-zero code on any failures

**PROVEN PATTERN FROM v05**: Use temporary database (tempfile.mkdtemp) for isolation. Display results in a rich Panel with a Table showing test names, status (checkmark/X), and details. This enables CI/CD integration and fast developer feedback.

---

## 9. Fixtures (required)

Create at least two fixture files:

### 9.1 `fixtures/sample_minimal.jsonl`
- 1 channel, 1 day, 5–10 messages
- includes at least 1 link, 1 blocker, 1 question

### 9.2 `fixtures/sample_3days.jsonl`
- 3 channels (`alice`, `bob`, `team-foo`)
- 3 consecutive days
- deliberately include changes:
  - a topic that appears day1 and disappears day3
  - a blocker introduced day1 and resolved day2
  - a "finished" item only on day2
  - new links introduced day2
  - at least 1 help request on day3

Fixture format (one JSON object per line):
```json
{"message_id":"m1","channel_id":"c-alice","channel_name":"alice","author_id":"u1","author_name":"Alice","created_at":"2026-01-15T09:10:00+09:00","content":"Started indexing pipeline. Repo: https://github.com/org/repo","attachments":[]}
```

---

## 10. Event-Driven Architecture (REQUIRED)

### 10.1 Purpose
An event-driven architecture provides:
- **Loose coupling**: Components communicate through events, not direct calls
- **Extensibility**: New features can subscribe to existing events
- **Observability**: Event history provides audit trail
- **Testability**: Events can be monitored and asserted in tests

**PROVEN IN v05**: Event-driven architecture was key to achieving 9.7/10 score. It enabled clean separation of concerns and made testing straightforward.

### 10.2 Required Event Types

You MUST implement these event types:

1. **MESSAGE_INGESTED**: Emitted when messages are loaded
   - Data: `count`, `channel_name`, `date`

2. **STATE_GENERATED**: Emitted when a daily state is created
   - Data: `channel_name`, `date`, `topics_count`, `has_blockers`

3. **DELTA_COMPUTED**: Emitted when a delta is calculated
   - Data: `channel_name`, `date`, `compared_to`, `new_items_count`, `resolved_items_count`

4. **DIGEST_CREATED**: Emitted when global digest is generated
   - Data: `date`, `channels_count`, `highlights_count`, `help_requests_count`

5. **ERROR**: Emitted when an error occurs
   - Data: `error_message`, `context`

### 10.3 EventBus Implementation Requirements

The EventBus MUST support:
- `subscribe(event_type, callback)`: Subscribe to events
- `unsubscribe(event_type, callback)`: Unsubscribe from events
- `publish(event)`: Publish an event to all subscribers
- `get_history(event_type=None)`: Get event history, optionally filtered
- `clear_history()`: Clear event history
- `enable()/disable()`: Enable/disable event publishing
- Event history tracking for debugging/observability

**CRITICAL PATTERN FROM v05**: Subscriber error isolation. Wrap all subscriber callbacks in try/except so one failing subscriber doesn't break the bus:

```python
def publish(self, event: Event) -> None:
    if not self._enabled:
        return
    self._history.append(event)
    if event.type in self._subscribers:
        for callback in self._subscribers[event.type]:
            try:
                callback(event)
            except Exception:
                # Don't let subscriber errors break the bus
                pass
```

### 10.4 Integration Points

Events MUST be emitted at these points:
- During message ingestion
- After state generation
- After delta computation
- After digest creation
- On errors (with proper error handling to not break the pipeline)

**PROVEN PATTERN FROM v05**: Inject EventBus via dependency injection. Components receive EventBus in constructor, not from globals. This enables testing with mock EventBus instances.

---

## 11. Testing Requirements (YOU MUST RUN THEM)

### 11.1 Test Coverage Requirements

The test suite MUST include at minimum:
- **53+ tests total** (baseline from v05, which achieved 89 tests for 9.7/10 score):
  - 7+ database tests (v05 achieved 19)
  - 8+ delta tests (v05 achieved 9)
  - 10+ timewindow tests (v05 achieved 11)
  - 13+ event system tests (v05 achieved 13)
  - 9+ summarizer tests (mock mode) (v05 achieved 13)
  - 6+ end-to-end tests (v05 achieved 6)

**PROVEN SUCCESS METRIC**: v05 achieved 89 tests (67% above minimum) and scored 9.7/10. Higher test coverage correlates strongly with implementation quality.

### 11.2 Unit tests
- DB schema creation and basic insert/query
- Time window computation (date/range/last-hours)
- Delta computation correctness (set diffs)
- Renderer output formatting (basic assertions)
- **Event bus functionality** (subscribe, publish, history, filtering, error isolation)

**CRITICAL PATTERN FROM v05**: Test subscriber error isolation to ensure one failing subscriber doesn't break the entire event bus.

### 11.3 Integration tests (mock LLM)
To make tests deterministic and cheap:
- Implement `--mock` mode that returns canned JSON for known inputs
- Use mock mode in CI/unit tests
- Test event emissions and subscriptions
- Verify event history contains expected events with correct data

**PROVEN PATTERN FROM v05**: Event tracking in tests provides behavioral verification, not just return value checking. Subscribe to events in tests and assert they were published with correct data.

### 11.4 End-to-end tests (real GLM4.7)
Add one e2e test that runs only when `GLM_API_KEY` is present:
- ingest minimal fixture
- run `preview --date ... --channel-name alice`
- assert that output is non-empty and valid JSON/state saved
- Keep it minimal to control cost

### 11.5 "Human-like self-testing" (mandatory)
After implementing, run these manual-like steps programmatically in `selftest`:
1) Create temporary database (isolated from real data)
2) Ingest `sample_minimal.jsonl` or `sample_3days.jsonl`
3) Run summaries for each date in range
4) Read back stored states/deltas from SQLite
5) Validate:
   - States exist for each day/channel
   - Deltas exist for day 2+ and contain expected "new" items
   - Digest rolls up highlights across channels
6) Display results in a rich table with PASS/FAIL indicators
7) Exit with non-zero code on any failures

**PROVEN PATTERN FROM v05**: Use temporary database (tempfile.mkdtemp) for isolation. Display results in a rich Panel with a Table showing test names, status (checkmark/X), and details.

### 11.6 Test Organization

Use pytest with:
- `conftest.py` for shared fixtures (database, event bus, sample messages)
- `tests/test_*.py` for module-specific tests (test_db.py, test_events.py, etc.)
- `tests/test_e2e_offline.py` for end-to-end integration tests
- `pytest-asyncio` for async test support (if needed)

**PROVEN PATTERN FROM v05**: Use tempfile.NamedTemporaryFile for database tests to ensure isolation. Clean up files in finally blocks.

---

## 12. Acceptance Criteria (Phase 1 is DONE when…)

1) `ingest` works and populates SQLite with beautiful progress output
2) `run --date` generates and stores:
   - `daily_channel_state`
   - `daily_channel_delta` (if previous day exists)
   - `global_digest`
3) `run --start --end` works over multiple days and produces deltas chained correctly
4) `run --last-hours` works for fast dev iteration
5) `selftest` passes on a clean machine (given fixtures)
6) With `GLM_API_KEY` set, `preview` succeeds using GLM4.7 and stores results
7) Outputs are readable Markdown and JSON is schema-valid
8) **Event-driven architecture is implemented and working**
9) **CLI provides beautiful rich output with progress bars, tables, and panels**
10) **53+ tests pass**, covering all major components including events

---

## 13. Implementation Notes (Important)

### 13.1 Architecture Patterns

**Event-Driven Architecture:**
- Implement an EventBus for pub/sub communication
- Emit events at key pipeline points
- Use event history for debugging and observability
- Components should be loosely coupled through events

**Separation of Concerns:**
- `core/events.py`: Event system (EventBus, Event types)
- `core/models.py`: Pydantic data models
- `core/summarizer.py`: State generation logic
- `core/delta.py`: Delta computation
- `core/digest.py`: Digest aggregation
- `core/renderer.py`: Markdown and rich rendering
- `infra/db.py`: SQLite operations
- `infra/glm_client.py`: LLM API client
- `infra/fixtures.py`: Fixture loading

**Make the core pipeline pure and testable:**
- core functions should accept Python objects / dicts, not DB cursors
- Use dependency injection for the EventBus

### 13.2 CLI/UX Best Practices

**Rich Output:**
- Use `rich.progress.Progress` for long-running operations
- Use `rich.table.Table` for structured data
- Use `rich.panel.Panel` for highlighted information
- Use color consistently: green (success), red (error), yellow (warning), cyan (info)
- Use status indicators: ✓ (success), ✗ (error), ⚠ (warning)

**Error Handling:**
- Provide clear, actionable error messages
- Use panels for important messages
- Log errors but don't show full tracebacks to users (unless --debug)

### 13.3 Logging

- Log responsibly:
  - do not print full message corpora unless `--debug`
- Use event history for observability
- Log timing information for performance monitoring

---

## 14. Deliverables Checklist

- [ ] Working CLI: `ingest`, `run`, `preview`, `selftest`
- [ ] SQLite schema + migrations/init
- [ ] Fixture files (2)
- [ ] Core summarization pipeline (GLM + chunking)
- [ ] Delta logic (code-based)
- [ ] Markdown renderer for summary/delta/digest
- [ ] **Rich terminal output** (progress bars, tables, panels)
- [ ] **Event-driven architecture** (EventBus + event types)
- [ ] **53+ comprehensive tests** (unit + integration + e2e)
- [ ] README with "Quick Start" commands

---

## 15. Quick Start (for README)

Example commands you MUST support:

```bash
# reset and ingest
python -m app.cli ingest --db data/app.db --fixture fixtures/sample_3days.jsonl --reset

# run for a specific date
python -m app.cli run --db data/app.db --date 2026-01-16

# run for a range (chained deltas)
python -m app.cli run --db data/app.db --start 2026-01-15 --end 2026-01-17

# fast dev loop (last 1 hour)
python -m app.cli run --db data/app.db --last-hours 1

# preview a single channel
python -m app.cli preview --db data/app.db --date 2026-01-17 --channel-name alice

# autonomous self-test
python -m app.cli selftest

# run tests
pytest tests/

# run tests with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## 16. Lessons Learned from v05 (Best Variant - 9.7/10)

The v05 implementation achieved a 9.7/10 score with 89 tests passing (67% above the 53+ requirement). This section documents what made v05 successful so future implementations can replicate these patterns.

### 16.1 Architectural Patterns That Worked

#### Event-Driven Architecture (EDA)

**What v05 did:**
- Implemented a lightweight EventBus with pub/sub pattern
- Defined 5 core event types: MESSAGE_INGESTED, STATE_GENERATED, DELTA_COMPUTED, DIGEST_CREATED, ERROR
- Used dataclasses for Event objects with automatic timestamps
- Injected EventBus into components via dependency injection

**Why it worked:**
- **Loose coupling**: Components don't need direct references to each other
- **Observability**: Event history provides audit trail for debugging
- **Extensibility**: New features can subscribe to existing events without modifying core logic
- **Testability**: Events can be monitored and asserted in tests

**Key implementation details from v05:**
```python
# EventBus with error isolation - subscriber errors don't break the bus
def publish(self, event: Event) -> None:
    if not self._enabled:
        return
    self._history.append(event)
    if event.type in self._subscribers:
        for callback in self._subscribers[event.type]:
            try:
                callback(event)
            except Exception:
                # Don't let subscriber errors break the bus
                pass
```

**Critical pattern: Error isolation in subscribers.** If a subscriber throws an exception, other subscribers still run. This prevents cascading failures.

#### Pure SQLite (No ORM)

**What v05 did:**
- Used sqlite3 module directly with parameterized queries
- Handled JSON serialization/deserialization manually
- Created proper indexes on (channel_id, created_at) and (channel_name, created_at)
- Used connection-per-operation pattern (simple, no connection pooling needed)

**Why it worked:**
- **Simplicity**: No ORM learning curve or magic behavior
- **Performance**: Direct SQL is fast and predictable
- **Debuggability**: SQL queries are visible and testable
- **Portability**: No ORM version conflicts or migrations

**Key pattern:**
```python
# Parameterized queries prevent SQL injection
cursor.execute(
    "SELECT * FROM messages WHERE channel_name = ? AND created_at >= ?",
    (channel_name, start_time)
)
```

#### Dependency Injection for Testability

**What v05 did:**
- Passed EventBus as optional parameter to Database constructor
- GLMClient received EventBus for publishing events
- Components received dependencies via constructor, not globals

**Why it worked:**
- Tests can inject mock EventBus for event tracking
- Tests can run without real GLM API calls
- No hidden global state makes tests deterministic

### 16.2 CLI/UX Patterns That Delighted Users

#### Rich Terminal Output

**What v05 did:**
- Used `rich` library for all CLI output
- Progress bars for long-running operations (ingest, run)
- Tables for structured data (ingest summary, messages, test results)
- Panels for highlighted information (summaries, deltas, digests, self-test)
- Consistent color coding: green (success), red (error), yellow (warning), cyan (info)

**Why it worked:**
- **Professional appearance**: Tool feels polished and production-ready
- **User feedback**: Progress bars show operations are running
- **Scannability**: Tables and panels make output easy to understand
- **Emotional design**: Colors convey meaning instantly

**Key patterns from v05:**
```python
# Progress bars for long operations
with Progress() as progress:
    task = progress.add_task("[green]Ingesting messages...", total=len(messages))
    db.insert_messages(messages)
    progress.update(task, completed=len(messages))

# Tables for structured data
table = Table(title="Ingest Summary", show_header=True, header_style="bold magenta")
table.add_column("Channel", style="cyan")
table.add_column("Messages", justify="right", style="green")

# Panels for highlighted info
panel = Panel(md, title=f"[bold blue]#{channel_name}[/bold blue]", border_style="blue")
```

#### Self-Test Command

**What v05 did:**
- Implemented `selftest` command that runs full pipeline validation
- Used temporary database for isolated testing
- Displayed results in a rich table with PASS/FAIL indicators
- Exited with non-zero code on failures

**Why it worked:**
- **Fast validation**: Developers can verify installation in seconds
- **Isolation**: Tests don't pollute real database
- **Clear output**: Table format shows exactly what passed/failed
- **CI/CD ready**: Exit codes enable automation

### 16.3 Testing Patterns That Provided Confidence

#### Comprehensive Test Coverage (89 tests)

**What v05 achieved:**
- 19 database tests (schema, CRUD, events)
- 9 delta tests (state comparison, diff logic)
- 11 timewindow tests (date parsing, ranges, timezone)
- 13 event system tests (pub/sub, history, filtering)
- 13 summarizer tests (mock mode, link extraction)
- 6 e2e tests (full pipeline)
- 18 other tests (fixtures, models, rendering)

**Why this level of coverage mattered:**
- **Refactoring safety**: Changes can be made with confidence
- **Edge case coverage**: Time zones, missing data, error conditions
- **Documentation**: Tests serve as executable examples
- **Regression prevention**: Bugs are caught early

#### Mock Mode for Deterministic Testing

**What v05 did:**
- Implemented `--mock` flag in GLMClient
- Mock mode returns predictable JSON responses
- All tests use mock mode by default
- Only e2e tests use real GLM API when available

**Why it worked:**
- **Speed**: Tests run in 0.16s without network calls
- **Cost**: No API charges during development
- **Determinism**: Same inputs produce same outputs
- **Offline development**: Tests work without API keys

**Key pattern:**
```python
# Mock mode enables fast, reliable tests
glm_client = GLMClient(event_bus)
glm_client.enable_mock_mode()
state = generate_state(channel_name, date, messages, glm_client, mock=True)
```

#### Event Tracking in Tests

**What v05 did:**
- Tests subscribe to events and assert they were published
- Event history is queried and validated
- Event data is checked for correctness
- Event order is verified for time-sensitive operations

**Why it worked:**
- **Behavioral verification**: Tests assert what happened, not just return values
- **Integration testing**: Events prove components are wired correctly
- **Debugging aid**: Event history shows execution flow

**Example from v05:**
```python
# Track events in tests
message_events = []
state_events = []
event_bus.subscribe(EventType.MESSAGE_INGESTED, lambda e: message_events.append(e))
event_bus.subscribe(EventType.STATE_GENERATED, lambda e: state_events.append(e))

# Assert events were published
db.insert_messages(messages)
assert len(message_events) > 0
```

### 16.4 Error Handling Patterns That Prevented Crashes

#### Subscriber Error Isolation

**What v05 did:**
- Wrapped all subscriber callbacks in try/except
- Logged errors but didn't propagate them
- Other subscribers continued running even if one failed

**Why it worked:**
- **Resilience**: One bug doesn't break entire pipeline
- **Debugging**: Errors are logged but don't stop execution
- **Graceful degradation**: Partial results are better than no results

#### Database Error Handling

**What v05 did:**
- Used parameterized queries to prevent SQL injection
- Validated dates and other inputs before database operations
- Returned None for missing data instead of raising exceptions
- Used context managers for database connections

**Why it worked:**
- **Security**: SQL injection is impossible with parameterized queries
- **Predictability**: Missing data returns None, not exceptions
- **Resource safety**: Context managers ensure connections close

### 16.5 Data Model Patterns That Ensured Consistency

#### Pydantic Schemas Everywhere

**What v05 did:**
- Defined all data models as Pydantic BaseModel subclasses
- Used Field(default_factory=list) for mutable defaults
- Validated JSON from database using model_validate_json()
- Serialized to JSON using model_dump_json()

**Why it worked:**
- **Type safety**: Pydantic validates types automatically
- **Serialization**: JSON conversion is handled correctly
- **Documentation**: Schemas serve as data contracts
- **IDE support**: Autocomplete and type checking work

**Key pattern:**
```python
class DailyChannelState(BaseModel):
    channel_name: str
    date: str
    topics: list[str] = Field(default_factory=list)  # Correct: avoids mutable default
    progress: Progress = Field(default_factory=Progress)
```

#### Stable State Schema for Deltas

**What v05 did:**
- Defined DailyChannelState schema as stable contract
- Deltas computed as set differences between states
- LLM prompted to output valid JSON matching schema
- Validation errors caught and reported immediately

**Why it worked:**
- **Reproducibility**: Same inputs produce same deltas
- **Debuggability**: Deltas can be computed manually for verification
- **Testability**: Mock states can predict delta results

### 16.6 Performance Patterns That Enabled Scale

#### Efficient Database Operations

**What v05 did:**
- Created compound indexes on (channel_id, created_at) and (channel_name, created_at)
- Used INSERT OR REPLACE for idempotent inserts
- Batched multiple messages in single transaction
- Selected only needed columns (no SELECT *)

**Why it worked:**
- **Fast queries**: Indexes make date-range queries fast
- **Idempotence**: Re-running ingest doesn't create duplicates
- **Transaction efficiency**: Batch operations are faster

### 16.7 Code Organization Patterns That Improved Maintainability

#### Clear Separation of Concerns

**What v05 did:**
- `core/`: Business logic (models, events, summarizer, delta, digest, renderer)
- `infra/`: Infrastructure (database, GLM client, fixtures)
- `app/`: CLI entry point
- Each module has single responsibility

**Why it worked:**
- **Navigate**: Code is easy to find
- **Test**: Each module can be tested independently
- **Replace**: Infrastructure can be swapped without changing core logic

#### Pure Functions for Core Logic

**What v05 did:**
- `compute_delta()` is pure function: same inputs produce same outputs
- `generate_digest()` doesn't touch database directly
- `render_*()` functions convert models to strings
- Core functions accept Python objects, not database cursors

**Why it worked:**
- **Testability**: Pure functions are easy to test
- **Reasoning**: No hidden state to track
- **Reuse**: Functions can be used in different contexts

---

## RUN

```bash
python -m app.cli selftest
```

---

**End of spec.**
