# Building a Discord Simulator: How We Developed a Digest Pipeline Without Real Data

**How realistic message simulation enabled us to build and test an LLM-powered summarizer months before Discord integration.**

---

## The Chicken-and-Egg Problem

We wanted to build a Discord daily digest system powered by LLMs. But we faced a classic development dilemma:

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

**The solution**: Build a realistic Discord message simulator that generates authentic-looking data for development and testing.

---

## Why Simulation Matters

### The Traditional Approach (and why it fails)

```python
# Bad: Writing test messages by hand
test_messages = [
    "Hey, did you fix the bug?",
    "Yeah, deployed it.",
    "Great, thanks!",
]

# Problem: Too simple, unrealistic, doesn't exercise edge cases
```

### Our Approach: Generate Thousands of Realistic Messages

```bash
# One command, 100 realistic messages
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --count 100 \
    --channels dev,test,general \
    --scenario standup \
    --sequential
```

Result: 100 messages with realistic patterns, timestamps, authors, URLs, and context.

---

## The Simulator Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DummyDataGenerator                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Scenarios   │  │ Distribution │  │   Timing     │          │
│  │               │  │   Modes      │  │   Engine     │          │
│  │ • standup     │  │ • random     │  │ • random     │          │
│  │ • bug-triage  │  │ • exact      │  │ • sequential │          │
│  │ • feature     │  │ • weighted   │  │ • hour range │          │
│  │ • random      │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 Template Engine                           │   │
│  │  "{emoji} Yesterday: {yesterday}. Today: {today}..."     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Authors   │  │   Content    │  │   Metadata   │          │
│  │  Generator   │  │   Generator  │  │   Generator  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              v
                    ┌─────────────────┐
                    │ MessageEvent[]  │
                    │   (100 msgs)    │
                    └─────────────────┘
```

---

## Scenario-Based Generation

Different team activities have different communication patterns. We built **scenarios** to match reality.

### 1. Standup Scenario

```python
templates = [
    "{emoji} Yesterday: {yesterday}. Today: {today}. Blockers: {blockers}",
    "Finished {task}. Working on {task_next}. No blockers.",
    "Blocked on {blocker}. Need help with {help_topic}.",
    "Made progress on {task}. {status}.",
    "Quick update: {update}",
]

tasks = [
    "implementing authentication",
    "fixing the login bug",
    "adding new features",
    "refactoring code",
    "writing tests",
]
```

**Output:**
```
🚀 Yesterday: implemented authentication. Today: fixing the login bug. Blockers: none
✅ Finished writing tests. Working on refactoring code. No blockers.
⚠️ Blocked on API rate limit. Need help with database query.
```

### 2. Bug-Triage Scenario

```python
templates = [
    "Bug report: {bug}. Priority: {priority}. Reproducible: {repro}",
    "Investigating {issue}. Found root cause: {cause}",
    "Fixed {bug}. Deploying to {env}.",
    "Can someone reproduce {bug}?",
    "{bug} is actually a feature request. Moving to backlog.",
    "Hotfix needed for {bug}. Affects {users} users.",
]

bugs = [
    "login not working",
    "page crashes on Safari",
    "API timeout errors",
    "memory leak in worker",
    "database connection issues",
]
```

**Output:**
```
Bug report: API timeout errors. Priority: critical. Reproducible: yes
Investigating page crashes on Safari. Found root cause: race condition
Fixed login not working. Deploying to staging.
Hotfix needed for memory leak in worker. Affects 500 users.
```

### 3. Feature-Discussion Scenario

```python
templates = [
    "Proposal: {feature}. Thoughts?",
    "What do you think about {idea}?",
    "I suggest we {suggestion}. This would {benefit}.",
    "Concerns about {feature}: {concern}",
    "Let's schedule a call to discuss {topic}.",
    "PR is ready for review: {pr_url}",
    "Documentation for {feature} is ready: {doc_url}",
]
```

**Output:**
```
Proposal: add dark mode. Thoughts?
I suggest we use Redis for caching. This would improve performance.
Concerns about implementing search: adds complexity
PR is ready for review: https://github.com/org/repo/pull/234
```

---

## Distribution Modes

Real Discord servers don't have uniform activity. We needed **distribution modes** to simulate reality.

### 1. Random Distribution (Default)

```bash
python -m src.app generate-dummy --count 100 --channels dev,test,general
```

Messages distributed randomly across channels:
- `#dev`: ~33 messages
- `#test`: ~33 messages
- `#general`: ~33 messages

### 2. Exact Distribution

Sometimes you need precise control:

```bash
python -m src.app generate-dummy \
    --messages-per-channel "dev:50,test:30,general:20"
```

Result:
- `#dev`: exactly 50 messages
- `#test`: exactly 30 messages
- `#general`: exactly 20 messages

**Implementation:**
```python
def parse_messages_per_channel(spec: str, channels: list[str]) -> dict[str, int]:
    """Parse 'dev:50,test:30,general:20' into dict."""
    result = {}
    for part in spec.split(","):
        channel, count_str = part.split(":")
        if channel not in channels:
            raise ValueError(f"Unknown channel: {channel}")
        result[channel] = int(count_str)
    return result
```

### 3. Weighted Distribution

For realistic activity patterns (some channels are busier):

```bash
python -m src.app generate-dummy \
    --weighted-channels "dev:70,test:20,general:10" \
    --count 100
```

Result:
- `#dev`: ~70 messages (70% of total)
- `#test`: ~20 messages (20% of total)
- `#general`: ~10 messages (10% of total)

**Implementation:**
```python
def distribute_messages_weighted(count: int, weights: dict[str, int]) -> list[str]:
    """Distribute messages by weight."""
    total_weight = sum(weights.values())
    distribution = []
    for i in range(count):
        rand_val = random.randint(1, total_weight)
        cumulative = 0
        for channel, weight in weights.items():
            cumulative += weight
            if rand_val <= cumulative:
                distribution.append(channel)
                break
    return distribution
```

---

## The Sequential Feature

Testing time-based features required **chronological ordering**:

```bash
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --count 100 \
    --sequential \
    --hour-start 9 --hour-end 18
```

**What it does:**
- Spreads 100 messages evenly across 9 AM - 6 PM
- Maintains conversation order
- Adds small random jitter (±5% interval) for realism

**Implementation:**
```python
def _generate_timestamp(sequential_index: int, sequential_total: int) -> str:
    """Generate evenly-spaced timestamps."""
    start_dt = datetime.strptime(self.date, "%Y-%m-%d").replace(hour=9, minute=0, second=0)
    end_dt = datetime.strptime(self.date, "%Y-%m-%d").replace(hour=18, minute=0, second=0)

    total_seconds = int((end_dt - start_dt).total_seconds())
    base_offset = (sequential_index * total_seconds) // sequential_total

    # Add jitter for realism
    jitter = random.randint(-total_seconds // 200, total_seconds // 200)
    offset = max(0, min(total_seconds, base_offset + jitter))

    dt = start_dt + timedelta(seconds=offset)
    return dt.isoformat() + "+09:00"
```

---

## Putting It All Together

### Realistic Development Workflow

```bash
# 1. Generate 10 days of realistic data
for day in {20..29}; do
    date=$(printf "2026-01-%02d" $day)

    python -m src.app generate-dummy \
        --date $date \
        --messages-per-channel "dev:20,test:15,general:10" \
        --scenario standup \
        --sequential \
        --hour-start 9 --hour-end 18
done

# 2. Run the full digest pipeline
python -m src.app run \
    --start 2026-01-20 \
    --end 2026-01-29 \
    --channels dev,test,general

# 3. View results
sqlite3 data/app.db "SELECT date, channel_name, state_json FROM daily_channel_state;"
```

### Testing Edge Cases

```bash
# Test low-activity channels
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --messages-per-channel "dev:0,test:0,general:5"

# Test high-volume bursts
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --count 500 \
    --channels dev \
    --scenario bug-triage

# Test time-zone overlaps
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --weighted-channels "dev:70,test:30" \
    --hour-start 6 --hour-end 24
```

---

## The One-Liner Digest Use Case

The simulation feature enabled rapid iteration on our **one-liner digest** format.

### Before (Generic Categories)
```
**#dev**: bug fixes, testing, authentication
**#test**: bug fixes, testing
**#general**: general discussion
```

### After (Specific & Action-Oriented)
```
**#dev**: Building auth features, Fixed bugs (blocked by Auth problems)
**#test**: Completed testing (blocked by Auth problems)
**#general**: 5 messages from 3 team members
```

**How simulation helped:**
1. Generated 10 days × 3 channels = 30 different data sets
2. Tested prompt variations in minutes, not weeks
3. Identified edge cases (empty channels, repeated content, etc.)
4. Validated fallback logic without waiting for real Discord data

---

## The Developer Experience

### Command Discovery

```bash
$ python -m src.app generate-dummy --help

Usage: src.app generate-dummy [OPTIONS]

  Generate dummy Discord messages for debugging and simulation.

  Distribution Modes:
  • Default: Random distribution across channels
  • --messages-per-channel: Exact count per channel (e.g., 'dev:15,test:10')
  • --weighted-channels: Weighted distribution (e.g., 'dev:70,test:30')

  Examples:
  • generate-dummy --date 2026-01-20 --count 30 --channels general,dev
  • generate-dummy --date 2026-01-20 --messages-per-channel dev:15,test:15
  • generate-dummy --date 2026-01-20 --weighted-channels dev:70,test:30 --count 100
  • generate-dummy --date 2026-01-20 --sequential --scenario standup
  • generate-dummy --date 2026-01-20 --scenario bug-triage --authors 3
  • generate-dummy --date 2026-01-20 --output test_data.jsonl --no-ingest

Options:
  --date, -d TEXT       Target date (YYYY-MM-DD) [required]
  --count, -n INTEGER   Number of messages to generate [default: 20]
  --channels, -c TEXT   Comma-separated channel names [default: general]
  --scenario, -s TEXT   Scenario: random, standup, bug-triage, feature-discussion
  --sequential          Generate messages in time order
  --output, -o PATH     Save to JSONL file instead of database
```

### Output Options

#### Direct to Database
```bash
python -m src.app generate-dummy --date 2026-01-20 --ingest
```

#### To JSONL File
```bash
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --output fixtures/test_data.jsonl \
    --no-ingest

# Use later for testing
python -m src.app ingest --fixture fixtures/test_data.jsonl
```

---

## What Simulation Enabled Us to Build

**Without real Discord data, we successfully:**

1. ✅ Developed and tested the full summarization pipeline
2. ✅ Iterated on LLM prompts 20+ times
3. ✅ Validated delta computation logic
4. ✅ Built digest generation across multiple channels
5. ✅ Tested edge cases (empty channels, high volume, etc.)
6. ✅ Created a rich CLI with progress tracking
7. ✅ Wrote comprehensive tests

**All before writing a single line of Discord integration code.**

---

## The Technical Details

### Message Structure

```python
message = MessageEvent(
    message_id=f"msg-{date}-{counter:04d}",
    channel_id=f"c-{channel}",
    channel_name=channel,
    author_id=author["id"],
    author_name=author["name"],
    created_at=created_at,  # ISO8601 with timezone
    content=content,        # Generated from template
    attachments=attachments if include_attachments else [],
    links=extract_links(content) if include_links else [],
)
```

### Author Generation

```python
def _generate_authors(count: int) -> list[dict]:
    """Generate fake author profiles."""
    first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey",
                   "Riley", "Jamie", "Quinn", "Avery", "Blake"]
    return [
        {"id": f"u-{i+1:03d}", "name": random.choice(first_names)}
        for i in range(count)
    ]
```

### Link Extraction

```python
FAKE_DOMAINS = [
    "github.com/org/repo",
    "docs.example.com/api",
    "jira.example.com/TICKET-123",
    "stackoverflow.com/questions/12345",
]

def _extract_links(content: str) -> list[str]:
    """Extract fake URLs from content."""
    links = []
    for domain in FAKE_DOMAINS:
        if domain in content:
            links.append(f"https://{domain}")
    return links
```

---

## Performance & Scale

| Operation | Time | Output |
|-----------|------|--------|
| Generate 100 messages | <1s | JSONL + DB |
| Generate 1000 messages | ~2s | JSONL + DB |
| Ingest 1000 messages | <1s | SQLite |
| Full pipeline (100 msgs) | ~5 min | Digest output |

**We generated and tested over 10,000 messages during development.**

---

## Lessons Learned

### 1. Simulation > Real Data (for Development)

Real Discord data is:
- Hard to anonymize
- Inconsistent quality
- Not available when starting out

Simulated data is:
- Immediately available
- Covers edge cases
- Reproducible

### 2. Scenarios Capture Reality

Different team activities = different communication patterns. Our scenarios (standup, bug-triage, feature-discussion) made generated data feel authentic.

### 3. Distribution Modes Matter

Real servers don't have uniform activity. Weighted and exact distribution modes let us simulate realistic channel traffic patterns.

### 4. Sequential Ordering is Critical

For time-based features (digests, timelines), chronological message order is essential. The `--sequential` flag was a game-changer.

### 5. Output Flexibility

Supporting both database and JSONL output meant we could:
- Test with fresh data each run
- Share test datasets
- Build fixture libraries
- Reproduce bugs consistently

---

## What's Next for the Simulator

- [ ] Emoji per author (personalization)
- [ ] Message threading/reply chains
- [ ] Attachment variety (images, code files, PDFs)
- [ ] Channel-specific vocabulary
- [ ] Time-zone aware authors
- [ ] Sentiment variation (positive/negative days)

---

## The Discord Integration (When Ready)

When we do add Discord integration, it will be:

```python
# Real Discord (future)
discord_client = DiscordClient(token=DISCORD_TOKEN)
messages = discord_client.fetch_messages(
    channels=["dev", "test", "general"],
    after=datetime.now() - timedelta(days=1)
)

# Simulation (now)
messages = generate_dummy_messages(
    date="2026-01-20",
    count=100,
    channels=["dev", "test", "general"],
    scenario="standup"
)

# Same interface, same pipeline, same tests ✅
```

The summarizer doesn't care where messages come from.

---

## Try It Yourself

```bash
# Clone the repo
git clone https://github.com/your-org/discord-daily-summarizer
cd discord-daily-summarizer

# Generate your first dataset
python -m src.app generate-dummy \
    --date 2026-01-20 \
    --count 50 \
    --channels dev,test,general \
    --scenario standup \
    --sequential

# Run the digest pipeline
python -m src.app run --date 2026-01-20

# View the digest
sqlite3 data/app.db "SELECT content FROM messages WHERE channel_name='daily-digest';"
```

---

**Built with Python 3.12, too much coffee, and zero real Discord data.**

*The simulator isn't a workaround—it's a feature. It enabled us to build, test, and iterate on the entire digest pipeline months before Discord integration will exist.*

**Code**: `src/infra/dummy_generator.py` | **CLI**: `src/app/cli.py generate-dummy`
