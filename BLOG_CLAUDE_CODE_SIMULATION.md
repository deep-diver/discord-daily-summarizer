# Discord Daily Summarizer: AI-Powered Team Digests with Interactive Simulation

**How we built an LLM-powered digest pipeline and tested it with realistic data using Claude Code and GLM-4.7.**

---

## Overview

The **Discord Daily Summarizer** is an automated digest system that transforms noisy Discord channel activity into structured, actionable daily summaries. It extracts key topics, tracks progress, identifies blockers, and computes day-over-day deltas—all powered by Large Language Models.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Discord Daily Summarizer                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Discord Messages  →  LLM Analysis  →  Daily Digest  →  Delta      │
│   (noisy, chaotic)      (GLM-4.7)        (summary)      (tracking)   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **Multi-channel digest**: Consolidates activity across `#dev`, `#test`, `#general` into one daily summary
- **Intelligent extraction**: Topics, blockers, help requests, links, progress tracking
- **Delta computation**: Day-over-day change detection (new topics, resolved issues, progress updates)
- **LLM-powered**: Uses Z.ai's GLM-4.7 model for natural language understanding

---

## The Challenge: Building Without Real Data

We faced a classic development dilemma:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   We need Discord data to test the summarizer              │
│           BUT                                               │
│   We need a working summarizer before Discord integration  │
│                                                             │
│             Which comes first? 🐔                            │
└─────────────────────────────────────────────────────────────┘
```

### Why Pre-Generated Data Doesn't Work

Traditional approaches fail for several reasons:

```python
# Bad: Template-based generation
templates = [
    "Working on {task}",
    "Fixed {bug}",
    "Deployed to {env}",
]
# Problem: Too generic, lacks context, no conversation flow

# Bad: Hand-written test messages
messages = [
    "Hey, did you fix the bug?",
    "Yeah, deployed it.",
    "Great, thanks!",
]
# Problem: Unrealistic, doesn't exercise edge cases
```

### Our Solution: Interactive AI Simulation

Instead of pre-generating data, we built an interactive CLI that allows an AI (Claude Code) to manually craft realistic messages one at a time. This approach:

1. **Ensures realism**: Each message is crafted with context, author voice, and natural flow
2. **Enables narrative**: Messages follow a coherent story across days
3. **Supports debugging**: Add messages for specific dates with random business-hours timestamps
4. **Maintains flexibility**: No templates, no patterns—just natural conversation

---

## How the Simulation Works

### The Interactive CLI

We added an `add-message` command to the CLI:

```bash
python -m src.app add-message \
    --channel dev \
    --content "Just pushed the new authentication flow. The OAuth2 callback now properly handles token refresh." \
    --author "Sarah Chen" \
    --links "https://github.com/ourteam/backend/pull/342" \
    --date 2026-01-20
```

**Key features**:
- `--date`: Specify a past date for delta computation testing
- Random business-hours time (9 AM - 6 PM) for realism
- Automatic link extraction from content
- Direct database ingestion

### The Claude Code Workflow

Claude Code acts as a "synthetic team member," generating realistic Discord messages:

```python
# Claude Code crafts each message individually
messages = [
    {
        "channel": "dev",
        "author": "Sarah Chen",
        "content": "Just pushed the new authentication flow...",
        "date": "2026-01-20"
    },
    {
        "channel": "dev",
        "author": "Marcus Rodriguez",
        "content": "@Sarah Chen Nice! I was testing the payment processing...",
        "date": "2026-01-20"
    },
    # ... 70+ more messages across 10 days
]
```

**Why this works**:
- Claude Code understands context, tone, and technical vocabulary
- Messages reference each other naturally (`@Sarah Chen`, "PR #345")
- Topics evolve realistically (discovery → investigation → PR → review → deploy)
- Blockers emerge and get resolved authentically

---

## The 10-Day Sprint Scenario

We designed a realistic e-commerce **checkout optimization sprint** that played out over 10 days:

### Day 1-3: Sprint Kickoff & Initial Work

```
Jan 20: Sprint kickoff, authentication work, GraphQL federation
Jan 21: Performance profiling baseline (k6 tests)
Jan 22: Redis cache, frontend code-splitting, database batching
```

### Day 4: Code Review

```
Jan 23: PR reviews
- Frontend PR #403: code-splitting and lazy loading
- Backend PR #402: N+1 query fix, batched JOINs
```

### Day 5: BLOCKER DISCOVERED 🔴

```
Jan 24: Redis connection pool exhausted under load
Max_connections: 50 vs 100+ concurrent requests
```

The blocker emerged naturally from the narrative:

> "Investigating performance regression... found Redis connection pool exhausted under load (Max_connections 50 vs 100+ concurrent requests)"

### Day 6: BLOCKER RESOLVED ✅

```
Jan 25: Fixed Redis connection pool
- Implemented async queue with waiting mechanism
- Added DB fallback when Redis is unavailable
- Fixed code-splitting with prefetch hints
```

### Day 7-8: Deployment

```
Jan 26: Merged PRs, deployed to staging, full regression testing
Jan 27: Production deployment live
```

### Day 9-10: Post-Deployment

```
Jan 28: Hotfix for cache invalidation race conditions
Jan 29: Sprint 24 Review, production metrics showing stability
```

---

## The LLM: GLM-4.7 by Z.ai

We selected **Z.ai's GLM-4.7** model for summarization. Here's why.

### Why GLM-4.7?

| Factor | GLM-4.7 | Alternatives |
|--------|---------|--------------|
| **Cost** | Free tier available | GPT-4: paid |
| **Rate limits** | 5 concurrent requests (free) | Anthropic: stricter |
| **Context window** | 128K tokens | Sufficient for daily digests |
| **JSON mode** | Structured output | Essential for parsing |
| **Speed** | ~30-50s per summary | Acceptable for batch |

### The Prompt Engineering

GLM-4.7 requires careful prompt engineering for reliable JSON output:

```python
prompt = f"""Analyze the following Discord messages from channel #{channel_name} on {date}.

Messages:
{messages_json}

Return a JSON object with this exact structure:
{{
    "channel_name": "{channel_name}",
    "date": "{date}",
    "topics": ["topic1", "topic2"],
    "progress": {{
        "started": ["Task A"],
        "continued": ["Task B"],
        "finished": ["Task C"],
        "blocked": ["Task D"]
    }},
    "blockers": ["Blocker description"],
    "help_requests": ["Request description"],
    "artifacts": {{
        "links": ["https://..."],
        "repos": [],
        "docs": []
    }},
    "next_steps": ["Step 1", "Step 2"]
}}

Rules:
- Extract topics from message content, not just keywords
- Blockers should be specific and actionable
- Include all URLs found in messages
- Progress items should be concrete (e.g., "implementing X" not just "X")"""
```

### Handling Rate Limits

GLM's free tier has **undocumented rate limits** beyond the published concurrent request limits. We encountered frequent `429 Too Many Requests` errors.

**Solution**: Exponential backoff with 429-specific handling:

```python
# src/infra/glm_client.py
if status_code == 429:
    # Rate limit error - use much longer backoff (2-5 minutes)
    backoff = 120 + (attempt * 60)  # 120, 180, 240, 300 seconds
    self._audit_logger.log_security_alert(
        f"Rate limit hit, backing off for {backoff}s ({backoff//60}m {backoff%60}s)",
        AuditSeverity.LOW,
        details={"attempt": attempt, "backoff": backoff}
    )
    time.sleep(backoff)
```

**Results**:
- 30 channel summaries processed
- Average backoff: 3-4 minutes per 429 error
- Pipeline completed successfully despite rate limits

---

## Claude Code: The Synthetic Team Member

Claude Code played a crucial role in this simulation. Here's how it worked.

### Why Claude Code?

1. **Context awareness**: Understands technical concepts (OAuth2, Redis, GraphQL)
2. **Natural conversation**: Writes messages that sound like real developers
3. **Coherent narrative**: Maintains story consistency across 10 days
4. **Technical accuracy**: Uses correct terminology and realistic scenarios

### Example Message Generation

**User request**: "Write a message about discovering a Redis connection pool blocker"

**Claude Code output**:
```python
@Sarah Chen Had that same issue last month! You need to explicitly call
connection.close() in the finally block of your retry decorator.
Check out utils/redis.py:45
```

Notice the details:
- References a previous message (`@Sarah Chen`)
- Specific technical advice (`finally block`, `utils/redis.py:45`)
- Natural conversational tone

### The Simulation Process

```
┌─────────────────────────────────────────────────────────────────┐
│                    Simulation Workflow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DESIGN SCENARIO                                            │
│     - Define sprint goal (checkout optimization)                │
│     - Plan major milestones (kickoff, blocker, deploy)          │
│     - Identify key characters (Sarah, Marcus, Alex, etc.)       │
│                                                                 │
│  2. GENERATE MESSAGES (via Claude Code)                        │
│     - Each message crafted individually                         │
│     - Add via CLI: add-message --channel --content --date       │
│     - Random timestamp within business hours (9 AM - 6 PM)      │
│                                                                 │
│  3. RUN DIGEST PIPELINE                                        │
│     - python -m src.app run --start 2026-01-20 --end 2026-01-29 │
│     - GLM-4.7 analyzes each channel's messages                 │
│     - Generates daily summaries with topics, blockers, progress │
│     - Computes day-over-day deltas                             │
│                                                                 │
│  4. REVIEW RESULTS                                             │
│     - Check daily digests for accuracy                         │
│     - Verify delta computation (new topics, resolved blockers)  │
│     - Validate narrative coherence                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Results: What the Simulation Achieved

### Quantitative Results

| Metric | Value |
|--------|-------|
| **Messages generated** | 73 |
| **Channels** | 3 (dev, test, general) |
| **Days simulated** | 10 |
| **LLM API calls** | 30 summaries + 30 deltas |
| **Pipeline duration** | ~60 minutes (with rate limit backoffs) |
| **Errors** | 0 |

### Qualitative Results

**Realistic topics extracted**:
- Authentication flow (OAuth2 token refresh)
- Payment processing (Stripe webhook handlers)
- Performance optimization (Redis caching, database batching)
- Frontend optimization (code-splitting, lazy loading)
- GraphQL federation (schema stitching, circular dependencies)

**Accurate blocker tracking**:
```
Day 5: BLOCKER - Redis connection pool exhausted (50 vs 100+ concurrent)
Day 6: RESOLVED - Async queue + DB fallback + prefetch hints
```

**Meaningful deltas**:
```
New Topics (Jan 21): Performance profiling, Code-splitting, API serialization
Resolved Topics (Jan 21): Authentication flow, Unit testing, GraphQL federation
Finished Now (Jan 23): N+1 query fix, PR #402, Frontend PR #403
```

---

## Key Technical Insights

### 1. Interactive AI > Template Generation

Pre-generating thousands of messages with templates produces unrealistic data. Interactive crafting with Claude Code produces authentic conversation that:

- References previous context naturally
- Uses correct technical vocabulary
- Evolves topics organically over time
- Includes realistic edge cases (blockers, help requests, PR reviews)

### 2. Rate Limiting is Complex

GLM's published limits (5 concurrent requests) don't tell the whole story. We hit undocumented RPM/RPD limits that required:

- 2-5 minute backoffs for 429 errors
- Up to 4 retries per request
- Sequential channel processing (not concurrent)
- Patient monitoring (total pipeline time: ~60 minutes)

### 3. LLM Prompts Need Structure

Getting reliable JSON from GLM-4.7 required:

- Explicit JSON structure in the prompt
- Clear rules for each field
- Examples don't help—structure does
- Temperature around 0.2 for consistent output

### 4. Delta Computation is Powerful

Day-over-day deltas provide valuable context:

```
New Topics: What's fresh today
Resolved Topics: What was completed
Progress Changes: What moved forward
New Blockers: What's blocking now
Resolved Blockers: What was unblocked
```

This makes digests actionable for teams catching up after a day away.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Discord Messages                         │
│                    (stored in SQLite)                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────┐
│                      Digest Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Fetch messages for date + channel                           │
│  2. Call GLM-4.7 for channel state                              │
│  3. Fetch previous day's state                                  │
│  4. Call GLM-4.7 for delta computation                          │
│  5. Store state and delta in database                           │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────────┐
│                      Daily Digest                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Top Highlights                                                 │
│  Help Requests                                                  │
│  New Links                                                      │
│  Per-Channel Summaries                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files and Code

### Core Components

| File | Purpose |
|------|---------|
| `src/app/cli.py` | CLI interface with `add-message`, `run`, `preview` commands |
| `src/infra/glm_client.py` | GLM-4.7 API client with retry logic and rate limiting |
| `src/core/digest_pipeline.py` | Main pipeline orchestrating fetch → analyze → digest |
| `src/core/events.py` | Event bus for observability |
| `src/security/` | Input validation, rate limiting, audit logging |

### Key Code Snippets

**Add Message Command** (`src/app/cli.py`):
```python
@app.command()
def add_message(
    channel: str = typer.Option(..., "--channel", "-c"),
    content: str = typer.Option(..., "--content", "-m"),
    author: str = typer.Option("You", "--author", "-a"),
    date: str = typer.Option(None, "--date", "-d"),
) -> None:
    """Add a single message for interactive scenario building."""
    if date:
        base_dt = datetime.strptime(date, "%Y-%m-%d")
        hour = random.randint(9, 17)  # Business hours
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        message_dt = base_dt.replace(hour=hour, minute=minute, second=second)
    else:
        message_dt = datetime.now()

    message = MessageEvent(
        message_id=generate_message_id(),
        channel_id=f"c-{channel}",
        channel_name=channel,
        author_id=f"u-{hash(author) % 1000}",
        author_name=author,
        created_at=message_dt.isoformat() + "+09:00",
        content=content,
        links=extract_links(content),
        attachments=[],
    )

    repo = MessageRepository(db_path=DB_PATH)
    repo.add(message)
```

**GLM Client with Retry** (`src/infra/glm_client.py`):
```python
def _chat_with_retry(
    self,
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    max_retries: int = 4,
) -> str:
    """Send chat request with retries and exponential backoff."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return self._single_request(messages, model, temperature, max_tokens)

        except httpx.HTTPStatusError as e:
            last_error = e
            status_code = e.response.status_code

            if attempt < max_retries:
                if status_code == 429:
                    # Rate limit error - use much longer backoff (2-5 minutes)
                    backoff = 120 + (attempt * 60)
                    self._audit_logger.log_security_alert(
                        f"Rate limit hit, backing off for {backoff}s",
                        AuditSeverity.LOW,
                        details={"attempt": attempt, "backoff": backoff}
                    )
                    time.sleep(backoff)
                elif status_code >= 500:
                    backoff = 2**attempt
                    time.sleep(backoff)
                else:
                    break
            else:
                break

    raise GLMClientError(f"Request failed after {max_retries + 1} attempts")
```

---

## Running the Simulation

### Step 1: Add Messages (Interactive)

```bash
# Add a message for a specific date
python -m src.app add-message \
    --channel dev \
    --content "Just pushed the OAuth2 token refresh fix. No more session loss!" \
    --author "Sarah Chen" \
    --date 2026-01-20

# Add a message for today
python -m src.app add-message \
    --channel dev \
    --content "Deploying hotfix to staging in 10 minutes" \
    --author "Emma Watson"
```

### Step 2: Run the Digest Pipeline

```bash
# Run for a single date
python -m src.app run --date 2026-01-20

# Run for a date range
python -m src.app run \
    --start 2026-01-20 \
    --end 2026-01-29 \
    --channels dev,test,general
```

### Step 3: Preview Results

```bash
# Preview daily digest
python -m src.app preview --date 2026-01-20

# Preview channel state
python -m src.app preview --channel dev --date 2026-01-20

# Preview delta
python -m src.app preview --channel dev --date 2026-01-21 --delta
```

---

## What's Next?

### Immediate Improvements

- [ ] Switch to GLM-4-Flash for better rate limits (10 concurrent vs 5)
- [ ] Add batch processing for parallel channel summaries (within rate limits)
- [ ] Implement caching for repeated channel-date queries

### Long-Term Features

- [ ] Discord integration (real message ingestion)
- [ ] Webhook for automated daily digests
- [ ] Multi-day digest ("weekly summary")
- [ ] Custom digest templates per channel

---

## Lessons Learned

### 1. Simulation Quality Matters

Realistic simulation data is critical for testing LLM-powered systems. Template-based generation produces patterns that LLMs can exploit, leading to overfitted prompts that fail on real data.

### 2. Rate Limiting is Undocumented

API rate limits are often more complex than published docs suggest. Build retry logic early, log aggressively, and expect the unexpected.

### 3. Interactive AI is Powerful

Using Claude Code as a synthetic team member produced higher-quality test data than any template system could. The key was manual, message-by-message crafting with full context awareness.

### 4. Delta Computation is Valuable

Day-over-day deltas transform static summaries into actionable intelligence. Teams can quickly see what's new, what's resolved, and what needs attention.

---

## Conclusion

The Discord Daily Summarizer demonstrates a practical approach to building LLM-powered systems: **simulate first, integrate later**.

By combining:
- **Interactive AI simulation** (Claude Code)
- **Production-grade LLM** (GLM-4.7)
- **Robust engineering** (rate limiting, retries, audit logging)

We built and tested a complete digest pipeline **before** writing a single line of Discord integration code.

The result: A system that's ready for real data, because it was tested with realistic synthetic data from day one.

---

**Built with Python 3.12, Claude Code, GLM-4.7, and too much coffee.**

**Project**: [discord-daily-summarizer](https://github.com/your-org/discord-daily-summarizer)
**LLM**: [GLM-4.7 by Z.ai](https://open.bigmodel.cn/)
**AI Assistant**: [Claude Code by Anthropic](https://claude.ai/code)
