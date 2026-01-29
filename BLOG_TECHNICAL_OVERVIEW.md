# Building a Discord Daily Summarizer: From Chaos to Clarity with LLMs

**How we built an intelligent digest system that turns thousands of Discord messages into actionable daily summaries using Python, SQLite, and LLMs.**

---

## The Problem

Discord has become the de facto communication hub for many development teams. But with high-velocity teams comes information overload:

- **#dev** channel: 500+ messages per day
- **#general** channel: Water cooler conversations mixed with important announcements
- **#standup** channel: Updates scattered across different time zones
- **Result**: Critical context gets buried, blockers go unnoticed, and onboarding becomes a nightmare

**We needed a way to automatically digest daily Discord activity into concise, actionable summaries.**

---

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Discord JSONL │ -> │   SQLite DB     │ -> │   Summarizer    │
│   (Ingest)      │    │   (Messages)    │    │   (LLM Calls)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Daily Digest  │ <- │   Delta Engine  │ <- │   State Store   │
│   (Output)      │    │   (Changes)     │    │   (Daily Snap)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Core Components

| Component | Responsibility | Tech |
|-----------|---------------|------|
| **Ingest Pipeline** | Load JSONL fixtures into SQLite | `sqlite3`, `json` |
| **Message Store** | Query messages by date/channel | SQLite with FTS5 |
| **Summarizer** | Extract state via LLM | GLM-4.7 API |
| **Delta Engine** | Compute day-over-day changes | Pure Python |
| **Digest Generator** | Create cross-channel summaries | Markdown rendering |
| **CLI** | User interface with progress tracking | `typer`, `rich` |

---

## The Data Model

### Message Event

Every Discord message becomes a `MessageEvent`:

```python
@dataclass
class MessageEvent:
    message_id: str
    channel_id: str
    channel_name: str
    author_id: str
    author_name: str
    created_at: str  # ISO8601
    content: str
    attachments: list[Attachment]
    links: list[str]
```

### Daily Channel State

The LLM converts raw messages into structured state:

```python
@dataclass
class DailyChannelState:
    channel_name: str
    date: str
    topics: list[str]              # What was discussed
    progress: Progress              # Task tracking
    artifacts: Artifacts            # Links/repos/docs
    questions: list[str]            # Unanswered questions
    help_requests: list[str]        # People needing help
    next_steps: list[str]           # Action items
```

This structured output is key—it transforms unstructured chat into queryable data.

---

## LLM Prompt Engineering

The secret sauce is in the prompts. Here's our state extraction prompt:

```python
prompt = f"""You are a technical lead analyzing Discord messages for #{channel_name} on {date}.

Extract the following structured information from these messages:

1. **Topics**: Main discussion themes (3-5 bullet points)
2. **Progress**: Categorize work:
   - started: Tasks recently begun
   - continued: Ongoing work from previous days
   - finished: Completed tasks
   - blocked: Tasks with blockers (include blocker description)
3. **Artifacts**: Links, repos, docs mentioned
4. **Questions**: Unanswered technical questions
5. **Help Requests**: People explicitly asking for help
6. **Next Steps**: Action items for tomorrow

Respond ONLY with valid JSON matching this schema:
{json_schema}

Messages to analyze:
{messages_text}
"""
```

### Key Prompt Design Decisions

1. **JSON Schema First**: Explicit schema prevents parsing errors
2. **Role-Based Framing**: "You are a technical lead" sets the right context
3. **Output Constraints**: "ONLY with valid JSON" avoids conversational filler
4. **Category Definitions**: Clear boundaries for progress states

---

## Delta Computation

Once we have daily states, we compute what changed:

```python
def compute_delta(current: DailyChannelState, previous: DailyChannelState | None) -> DailyChannelDelta:
    if previous is None:
        return DailyChannelDelta(
            new_topics=current.topics,
            progress_changes=ProgressChanges(
                started_now=current.progress.started,
                finished_now=current.progress.finished,
                new_blockers=current.progress.blocked,
                resolved_blockers=[],
            ),
            # ...
        )

    return DailyChannelDelta(
        new_topics=[t for t in current.topics if t not in previous.topics],
        resolved_topics=[t for t in previous.topics if t not in current.topics],
        progress_changes=ProgressChanges(
            started_now=[t for t in current.progress.started if t not in previous.progress.started],
            finished_now=[t for t in current.progress.finished if t not in previous.progress.finished],
            new_blockers=[b for b in current.progress.blocked if b not in previous.progress.blocked],
            resolved_blockers=[b for t in previous.progress.blocked if b not in current.progress.blocked],
        ),
        # ...
    )
```

This gives us "what's new" instead of just "what happened."

---

## The Digest Pipeline

The digest combines deltas across all channels:

```python
def generate_digest(date: str, states: dict, deltas: dict, summaries: dict) -> DailyDigest:
    highlights = []
    blocker_count = 0
    all_links = []

    for channel_id, state in states.items():
        delta = deltas[channel_id]
        blocker_count += len(delta.progress_changes.new_blockers)

        # Top 3 highlights per channel
        if delta.new_topics:
            highlights.append(f"**#{state.channel_name}**: New topics: {', '.join(delta.new_topics[:3])}")
        if delta.progress_changes.finished_now:
            highlights.append(f"**#{state.channel_name}**: Finished: {', '.join(delta.progress_changes.finished_now[:3])}")
        if delta.progress_changes.new_blockers:
            highlights.append(f"**#{state.channel_name}**: BLOCKED: {', '.join(delta.progress_changes.new_blockers)}")

        all_links.extend(delta.new_links)

    return DailyDigest(
        date=date,
        highlights=highlights[:10],  # Top 10 overall
        blockers=blocker_count,
        links=dedupe(all_links),
    )
```

Output example:

```markdown
# Daily Digest for 2026-01-20

## Highlights

- **#dev**: New topics: API rate limiting, authentication refactoring
- **#test**: Finished: Integration tests for payment flow
- **#general**: BLOCKED: Database migration awaiting review

## Blockers
3 blockers across all channels - most critical: "API rate limit deployment blocked by code review"

## Links & Resources
- [PR #234] Add rate limiting to API gateway
- [Docs] Database migration guide
```

---

## CLI Experience

We built a rich CLI using `typer` and `rich`:

```bash
# Ingest Discord export
python -m src.app ingest --fixture discord_export.jsonl --reset

# Generate daily summary
python -m src.app run --date 2026-01-20 --channels dev,test

# Preview single channel
python -m src.app preview --channel-name dev --last-hours 24

# Run self-test
python -m src.app selftest --verbose
```

### Progress Tracking

Long-running LLM operations need visual feedback:

```python
with ProgressTracker(console, "Processing 10 channels", total=10) as tracker:
    for channel in channels:
        state = summarizer.generate_state(channel, date, messages)
        tracker.update(description=f"Completed #{channel}")
        tracker.advance(1)
```

---

## Error Handling & Retries

LLM APIs are unreliable. We built resilience:

```python
def _chat_with_retry(messages, model, temperature, max_tokens, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            return self._single_request(messages, model, temperature, max_tokens)
        except httpx.HTTPStatusError as e:
            if attempt < max_retries and e.response.status_code >= 500:
                backoff = 2 ** attempt  # Exponential backoff
                time.sleep(backoff)
                continue
            raise
    raise GLMClientError(f"Failed after {max_retries} retries")
```

---

## Testing Strategy

### Mock Mode for Development

Testing LLM pipelines is expensive. We added mock mode:

```python
glm_client = GLMClient(event_bus, mock=True)
# Returns pre-canned JSON responses without API calls
```

### Dummy Data Generator

For pipeline testing, we generate realistic fake messages:

```python
messages = generate_dummy_messages(
    date="2026-01-20",
    count=50,
    channels=["dev", "test", "general"],
    scenario="standup",  # or "bug-triage", "feature-discussion"
    sequential=True,      # Time-ordered
)
```

---

## Deployment & Operations

### Environment Variables

```bash
export GLM_API_KEY="your-key-here"
export DATABASE_PATH="data/app.db"
```

### Running the Pipeline

```bash
# 1. Ingest data
python -m src.app ingest --reset

# 2. Generate summaries
python -m src.app run --date 2026-01-20

# 3. Query stored state
sqlite3 data/app.db "SELECT state_json FROM daily_channel_state WHERE date='2026-01-20';"
```

---

## Lessons Learned

### 1. Schema-Driven LLM Outputs

**Lesson**: Free-form LLM outputs are fragile.

**Solution**: Use explicit JSON schemas and validate responses. We caught 30%+ parsing errors in development before this.

### 2. Delta > State

**Lesson**: Daily summaries alone miss trends.

**Solution**: Always compute deltas. "What changed" is more valuable than "what happened."

### 3. Mock Early, Mock Often

**Lesson**: LLM API calls are slow and expensive.

**Solution**: Build mock mode first. Our development cycle went from 5 min/run to 5 sec/run.

### 4. Keep Credentials Simple

**Lesson**: Encrypted credential files add complexity without real security.

**Solution**: Use environment variables. If someone can read your file, they can read your env vars too.

### 5. Rich CLI Feedback

**Lesson**: Silent CLI = confused users.

**Solution**: Progress bars, spinners, and status updates. Users need to know *what's happening* during 30-second LLM calls.

---

## Performance Metrics

| Operation | Time | Cost (w/ GLM-4.7) |
|-----------|------|------------------|
| Ingest 1K messages | 0.5s | $0 |
| Generate state (100 msgs) | 30s | ~$0.002 |
| Compute delta | <1s | $0 |
| Generate digest | <1s | $0 |
| **Full daily pipeline** | **~5 min** | **~$0.02** |

---

## What's Next?

- [ ] Discord bot integration (webhook ingestion)
- [ ] Multi-day trend analysis
- [ ] Sentiment analysis over time
- [ ] Automatic blocker escalation notifications
- [ ] Web dashboard for historical queries

---

## Code Repository

The full codebase is available at: `github.com/your-org/discord-daily-summarizer`

**Key Files to Explore:**
- `src/core/summarizer.py` - LLM integration
- `src/core/delta.py` - Change detection
- `src/infra/db.py` - SQLite layer
- `src/app/cli.py` - CLI interface

---

**Built with Python 3.12, SQLite, GLM-4.7, and too much coffee.**

*Questions? Open an issue or PR!*
