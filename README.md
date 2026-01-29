# Discord Message Summarizer

Discord message summarizer with real Discord API integration, SQLite storage, and GLM4.7 LLM-powered summaries.

## Features

- **Discord API Integration**: Fetch messages directly from Discord channels
- **Dual Summary Formats**: Choose between detailed (with deltas) or simple (3-sentence) summaries
- **SQLite Database**: Persistent storage for messages, states, deltas, and digests
- **GLM4.7 Integration**: Real LLM calls for generating daily channel states
- **Event-Driven Architecture**: Loose coupling and observability via EventBus
- **Rich CLI Output**: Beautiful terminal output with progress bars, tables, and panels
- **Simulation Mode**: Test with realistic chat personas (6 unique personalities)
- **Post Back to Discord**: Automatically post summaries to your Discord channels
- **GitHub Actions**: Automated daily summarization workflow

## Quick Start

### Installation

```bash
# Install core dependencies
pip install -e .

# Install with Discord integration
pip install -e ".[discord]"

# or with dev dependencies
pip install -e ".[dev,discord]"
```

### Setup

```bash
# Set GLM API key
export GLM_API_KEY="your-api-key-here"
```

### Usage

#### Discord Integration

```bash
# Fetch messages from Discord
export DISCORD_BOT_TOKEN="your-bot-token"
python -m app.cli fetch-discord \
  --token $DISCORD_BOT_TOKEN \
  --guild-id YOUR_GUILD_ID \
  --channels general,vibe-learning \
  --output discord_export.jsonl

# Generate simple 3-sentence summary and post to Discord
python -m app.cli run \
  --db data/app.db \
  --date 2026-01-16 \
  --simple \
  --post-to-discord \
  --discord-token $DISCORD_BOT_TOKEN

# Generate detailed summary with deltas
python -m app.cli run \
  --db data/app.db \
  --date 2026-01-16 \
  --post-to-discord \
  --discord-token $DISCORD_BOT_TOKEN

# Simulate test data for development
python -m app.cli simulate \
  --guild-id YOUR_GUILD_ID \
  --channel-id CHANNEL_ID \
  --days 3 \
  --messages-per-day 15 \
  --output simulation.jsonl
```

#### Local Development

```bash
# Ingest fixtures into database
python -m app.cli ingest --db data/app.db --fixture fixtures/sample_3days.jsonl --reset

# Run for a specific date
python -m app.cli run --db data/app.db --date 2026-01-16

# Run for a date range (chained deltas)
python -m app.cli run --db data/app.db --start 2026-01-15 --end 2026-01-17

# Fast dev loop (last 1 hour)
python -m app.cli run --db data/app.db --last-hours 1

# Simple 3-sentence summary mode
python -m app.cli run --db data/app.db --date 2026-01-16 --simple

# Preview a single channel
python -m app.cli preview --db data/app.db --date 2026-01-17 --channel-name alice

# Autonomous self-test
python -m app.cli selftest
```

### Testing

```bash
# Run all tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_db.py -v
```

## Project Structure

```
project-root/
  README.md
  pyproject.toml
  src/
    app/
      __init__.py
      cli.py                 # CLI commands
    core/
      __init__.py
      models.py              # Pydantic data models
      timewindow.py          # Time window logic
      summarizer.py          # LLM-based summarization (detailed)
      simple_summarizer.py   # LLM-based summarization (3-sentence)
      delta.py               # Delta computation
      digest.py              # Global digest aggregation
      renderer.py            # Markdown and rich rendering
      events.py              # Event-driven architecture
    infra/
      __init__.py
      db.py                  # SQLite operations
      glm_client.py          # GLM4.7 API client
      fixtures.py            # Fixture loading
      discord_fetcher.py     # Discord API integration
      discord_simulator.py   # Chat simulation with personas
  fixtures/
    sample_3days.jsonl       # 3-channel, 3-day fixture
    sample_minimal.jsonl     # Minimal test fixture
  tests/
    conftest.py              # Pytest fixtures
    test_db.py               # Database tests
    test_timewindow.py       # Time window tests
    test_delta.py            # Delta computation tests
    test_events.py           # Event system tests
    test_summarizer_mock.py  # Summarizer tests (mock mode)
    test_e2e_offline.py      # End-to-end tests
  .github/
    workflows/
      daily-summary.yml      # GitHub Actions workflow
  data/
    app.db                   # SQLite database (created at runtime)
```

## CLI Commands

### `fetch-discord`

Fetch messages from Discord API and save to JSONL.

```bash
python -m app.cli fetch-discord \
  --token $DISCORD_BOT_TOKEN \
  --guild-id YOUR_GUILD_ID \
  --channels general,vibe-learning \
  --output discord_export.jsonl
```

Options:
- `--token`: Discord bot token
- `--guild-id`: Discord server (guild) ID
- `--channels`: Comma-separated channel names (use `--list-only` to discover)
- `--output`: Output JSONL file path
- `--list-only`: List available channels and exit
- `--after`: Fetch messages after this date (YYYY-MM-DD)
- `--before`: Fetch messages before this date (YYYY-MM-DD)
- `--limit`: Maximum messages per channel (default: 1000)

### `simulate`

Generate simulated chat messages for testing.

```bash
python -m app.cli simulate \
  --guild-id YOUR_GUILD_ID \
  --channel-id CHANNEL_ID \
  --days 3 \
  --messages-per-day 15 \
  --output simulation.jsonl
```

Options:
- `--guild-id`: Discord server ID
- `--channel-id`: Channel ID for simulation
- `--days`: Number of days to simulate
- `--messages-per-day`: Messages per day (default: 20)
- `--pattern`: Activity pattern (normal/bursty/quiet, default: normal)
- `--output`: Output JSONL file path
- `--post-to-discord`: Also post to Discord (requires `--discord-token`)

### `ingest`

Ingest fixture messages into SQLite.

```bash
python -m app.cli ingest --db data/app.db --fixture fixtures/sample_3days.jsonl --reset
```

Options:
- `--db`: Path to SQLite database
- `--fixture`: Path to fixture file
- `--reset`: Reset database before ingest

### `run`

Run summarization pipeline.

```bash
# Simple 3-sentence summary
python -m app.cli run --db data/app.db --date 2026-01-16 --simple

# Detailed summary with deltas
python -m app.cli run --db data/app.db --date 2026-01-16

# Post to Discord
python -m app.cli run --db data/app.db --date 2026-01-16 \
  --post-to-discord --discord-token $DISCORD_BOT_TOKEN
```

Options:
- `--date`: Process specific date (YYYY-MM-DD)
- `--start --end`: Process date range
- `--last-hours N`: Process last N hours
- `--channels`: Comma-separated channel filter
- `--simple/-s`: Use simple 3-sentence format (no deltas)
- `--mock`: Use mock LLM responses
- `--dry-run`: Don't store results
- `--post-to-discord`: Post summary to Discord
- `--discord-token`: Discord bot token for posting

### `preview`

Preview a single channel's summary.

```bash
python -m app.cli preview --db data/app.db --date 2026-01-17 --channel-name alice
```

### `selftest`

Run autonomous self-test with temporary database.

```bash
python -m app.cli selftest
```

## Data Model

### MessageEvent

Input record representing a normalized Discord message:
- `message_id`: Unique identifier
- `channel_id`, `channel_name`: Channel information
- `author_id`, `author_name`: Author information
- `created_at`: ISO8601 timestamp
- `content`: Message content
- `attachments`: List of attachment metadata
- `links`: URLs extracted from content

### DailyChannelState

Structured JSON state generated by LLM:
- `topics`: Discussion topics
- `progress`: Started/continued/finished/blocked tasks
- `artifacts`: Links/repos/docs
- `questions`, `help_requests`, `next_steps`: Additional context

### DailyChannelDelta

Structured JSON delta comparing states:
- `new_topics`, `resolved_topics`: Topic changes
- `progress_changes`: Progress updates
- `new_links`, `new_help_requests`: New artifacts and requests

### GlobalDigest

Aggregated digest across channels:
- `highlights`: Top 5 highlights
- `help_requests`: Top 5 help requests
- `links`: Top 10 new links

### Simple Summary

Brief 3-sentence summary for quick reading:
- **Sentence 1**: What was discussed
- **Sentence 2**: Key outcomes or decisions
- **Sentence 3**: Blockers or next steps

## Architecture

### Event-Driven Architecture

Components communicate via `EventBus` for loose coupling:
- `MESSAGE_INGESTED`: Messages loaded
- `STATE_GENERATED`: Daily state created
- `DELTA_COMPUTED`: Delta calculated
- `DIGEST_CREATED`: Global digest generated
- `ERROR`: Error occurred

### Separation of Concerns

- **core/**: Business logic (models, events, summarizer, simple_summarizer, delta, digest, renderer)
- **infra/**: Infrastructure (database, GLM client, fixtures, discord_fetcher, discord_simulator)
- **app/**: CLI entry point

### Summary Formats

Two output formats available:

**Simple Mode** (`--simple`):
- 3-sentence summary
- No delta tracking
- No database storage
- Ideal for quick daily updates

**Detailed Mode** (default):
- Full structured state with topics, progress, artifacts
- Delta computation between days
- Global digest across channels
- Database persistence for historical analysis

### Testing Strategy

- **Unit tests**: Individual components in isolation
- **Integration tests**: Component interactions
- **E2E tests**: Full pipeline validation
- **Mock mode**: Fast, deterministic testing without API calls
- **Simulation mode**: Test with realistic chat personas

## Requirements

- Python 3.11+
- GLM API key (set as `GLM_API_KEY` environment variable)
- Discord bot token (for Discord integration, optional)

## Dependencies

```
# Core
typer>=0.9.0        # CLI framework
pydantic>=2.0.0     # Data validation
rich>=13.0.0        # Terminal output
python-dotenv>=1.0.0 # Environment variables
httpx>=0.24.0       # HTTP client (for GLM API)

# Discord (optional)
discord.py>=2.3.0   # Discord API integration

# Development
pytest>=7.0.0       # Testing framework
```

## GitHub Actions

See [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md) for setting up automated daily summaries.

### Features

- Scheduled runs at 9 PM KST (daily)
- Manual trigger support
- Automatic Discord posting
- Full pipeline: fetch → ingest → summarize → post

## License

MIT
