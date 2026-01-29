#!/usr/bin/env python3
"""Generate realistic Discord messages using AI templates."""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# Realistic tech team Discord messages for January 20, 2026

MESSAGES_2026_01_20 = [
    # #dev channel
    {
        "message_id": "msg-2026-01-20-001",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-001",
        "author_name": "Sarah Chen",
        "created_at": "2026-01-20T09:15:00+09:00",
        "content": "Just pushed the new authentication flow. The OAuth2 callback now properly handles token refresh without the session loss bug we saw on Friday.",
        "attachments": [],
        "links": ["https://github.com/ourteam/backend/pull/342"]
    },
    {
        "message_id": "msg-2026-01-20-002",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-002",
        "author_name": "Marcus Rodriguez",
        "created_at": "2026-01-20T09:22:00+09:00",
        "content": "@Sarah Chen Nice! I was testing the payment processing integration last night and found that the Stripe webhook handler needs better error handling for idempotency keys. Want me to open a PR?",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-003",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-003",
        "author_name": "Alex Kim",
        "created_at": "2026-01-20T09:45:00+09:00",
        "content": "Hey team, I'm debugging a memory leak in the background worker. Using memory_profiler I can see it's related to the Redis connection pool not releasing connections after failed retries. Anyone dealt with this before?",
        "attachments": [],
        "links": ["https://github.com/ourteam/backend/issues/789"]
    },
    {
        "message_id": "msg-2026-01-20-004",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-001",
        "author_name": "Sarah Chen",
        "created_at": "2026-01-20T10:02:00+09:00",
        "content": "@Alex Kim Had that same issue last month! You need to explicitly call connection.close() in the finally block of your retry decorator. Check out utils/redis.py:45",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-005",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-004",
        "author_name": "Emma Watson",
        "created_at": "2026-01-20T10:30:00+09:00",
        "content": "Deployed hotfix for the API rate limiting issue to staging. Production deploy scheduled for 2pm ET today. @DevOps please monitor the Grafana dashboard after deployment.",
        "attachments": [],
        "links": ["https://grafana.internal.com/d/api-rate-limit", "https://github.com/ourteam/backend/pull/344"]
    },
    {
        "message_id": "msg-2026-01-20-006",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-005",
        "author_name": "David Park",
        "created_at": "2026-01-20T11:15:00+09:00",
        "content": "Started working on the GraphQL federation for the new inventory service. The schema stitching is more complex than expected - we have some circular type dependencies between Product and Catalog services.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-007",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-002",
        "author_name": "Marcus Rodriguez",
        "created_at": "2026-01-20T11:45:00+09:00",
        "content": "PR #345 is ready for review - adds comprehensive unit tests for the checkout flow. Coverage went from 45% to 87% for cart.py 🎉",
        "attachments": [],
        "links": ["https://github.com/ourteam/backend/pull/345"]
    },
    {
        "message_id": "msg-2026-01-20-008",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-003",
        "author_name": "Alex Kim",
        "created_at": "2026-01-20T13:20:00+09:00",
        "content": "@Sarah Chen That fixed it! Memory usage is back to normal. Thanks for the quick help!",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-009",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-006",
        "author_name": "Lisa Zhang",
        "created_at": "2026-01-20T14:00:00+09:00",
        "content": "Heads up - we need to upgrade our Elasticsearch cluster from 7.17 to 8.11. The current version has a security vulnerability. Planning to do this Saturday morning, expect ~30min downtime.",
        "attachments": [],
        "links": ["https://nvd.nist.gov/vuln/detail/CVE-2025-12345"]
    },
    {
        "message_id": "msg-2026-01-20-010",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-004",
        "author_name": "Emma Watson",
        "created_at": "2026-01-20T15:30:00+09:00",
        "content": "Production deployment complete. Hotfix is live and API error rates have dropped from 12% to 0.3%. Monitoring dashboards looking healthy! 🚀",
        "attachments": [],
        "links": ["https://grafana.internal.com/d/api-errors"]
    },
    {
        "message_id": "msg-2026-01-20-011",
        "channel_id": "c-dev",
        "channel_name": "dev",
        "author_id": "u-005",
        "author_name": "David Park",
        "created_at": "2026-01-20T16:45:00+09:00",
        "content": "Made progress on the GraphQL federation! Using @key directives with custom resolvers solved the circular dependency issue. Draft PR is up for initial feedback.",
        "attachments": [],
        "links": ["https://github.com/ourteam/inventory/pull/23"]
    },

    # #test channel
    {
        "message_id": "msg-2026-01-20-101",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-007",
        "author_name": "Felix Andersson",
        "created_at": "2026-01-20T09:30:00+09:00",
        "content": "Morning all! Running the full integration test suite on staging. Found 2 flaky tests in the payment reconciliation module - they're timing out intermittently.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-102",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-008",
        "author_name": "Yuki Tanaka",
        "created_at": "2026-01-20T10:15:00+09:00",
        "content": "@Felix Andersson I'll look into those flaky tests. Saw similar issues before - usually caused by race conditions in the test database cleanup.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-103",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-009",
        "author_name": "Oliver Smith",
        "created_at": "2026-01-20T11:00:00+09:00",
        "content": "Created new E2E tests for the new user onboarding flow. Testing with Playwright now - the multi-step form validation is working but we have some issues with the progress indicator not updating correctly.",
        "attachments": [],
        "links": ["https://github.com/ourteam/e2e-tests/pull/56"]
    },
    {
        "message_id": "msg-2026-01-20-104",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-007",
        "author_name": "Felix Andersson",
        "created_at": "2026-01-20T13:00:00+09:00",
        "content": "Test results from this morning's run: 347 passed, 2 failed, 5 skipped. The failures are both in the webhook signature verification tests - investigating now.",
        "attachments": [],
        "links": ["https://ci.internal.com/run/45234"]
    },
    {
        "message_id": "msg-2026-01-20-105",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-008",
        "author_name": "Yuki Tanaka",
        "created_at": "2026-01-20T14:30:00+09:00",
        "content": "Fixed the flaky tests! Added proper await statements for the database cleanup operations and increased the timeout from 5s to 10s for slow CI runners.",
        "attachments": [],
        "links": ["https://github.com/ourteam/backend/pull/346"]
    },
    {
        "message_id": "msg-2026-01-20-106",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-009",
        "author_name": "Oliver Smith",
        "created_at": "2026-01-20T15:15:00+09:00",
        "content": "The E2E tests are passing now! Issue was a race condition in the progress indicator - it was checking completion status before the animation finished. Added waitForTimeout(500) to fix.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-107",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-010",
        "author_name": "Nina Patel",
        "created_at": "2026-01-20T16:00:00+09:00",
        "content": "Updated the load testing script to simulate 10,000 concurrent users during checkout. Peak load test scheduled for tomorrow at 2am. CC @DevOps",
        "attachments": [],
        "links": ["https://docs.internal.com/load-testing"]
    },
    {
        "message_id": "msg-2026-01-20-108",
        "channel_id": "c-test",
        "channel_name": "test",
        "author_id": "u-007",
        "author_name": "Felix Andersson",
        "created_at": "2026-01-20T17:30:00+09:00",
        "content": "Evening test run complete: all green! 🟢 349 passed, 0 failed. The fixes from today are working perfectly. Great work team!",
        "attachments": [],
        "links": ["https://ci.internal.com/run/45289"]
    },

    # #general channel
    {
        "message_id": "msg-2026-01-20-201",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-011",
        "author_name": "James Wilson",
        "created_at": "2026-01-20T08:00:00+09:00",
        "content": "Good morning everyone! ☀ Coffee's brewing in the kitchen if anyone needs a refill.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-202",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-012",
        "author_name": "Maria Garcia",
        "created_at": "2026-01-20T09:00:00+09:00",
        "content": "Reminder: Team lunch tomorrow at 12:30pm at Sakura Sushi. Please RSVP in #announcements if you're coming!",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-203",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-013",
        "author_name": "Tom Anderson",
        "created_at": "2026-01-20T10:00:00+09:00",
        "content": "Just shared the Q1 roadmap slides in #announcements. Key highlights: we're focusing on mobile app performance and launching the new analytics dashboard by March. Let me know if you have questions!",
        "attachments": [],
        "links": ["https://docs.internal.com/q1-roadmap"]
    },
    {
        "message_id": "msg-2026-01-20-204",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-014",
        "author_name": "Rachel Green",
        "created_at": "2026-01-20T11:30:00+09:00",
        "content": "Does anyone have recommendations for good Python profiling tools? I'm trying to optimize some data processing scripts that are taking too long.",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-205",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-003",
        "author_name": "Alex Kim",
        "created_at": "2026-01-20T11:45:00+09:00",
        "content": "@Rachel Green I've had great success with py-spy for live profiling and scalene for detailed analysis. py-spy is especially useful because it can profile without modifying your code!",
        "attachments": [],
        "links": ["https://github.com/benfred/py-spy", "https://github.com/plasma-umass/scalene"]
    },
    {
        "message_id": "msg-2026-01-20-206",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-015",
        "author_name": "Chris Lee",
        "created_at": "2026-01-20T13:00:00+09:00",
        "content": "Hey everyone, I'm conducting user interviews for the new dashboard feature this Thursday and Friday. If you know any power users who'd be interested in giving feedback, please let me know! $50 gift card for participants 🎁",
        "attachments": [],
        "links": []
    },
    {
        "message_id": "msg-2026-01-20-207",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-016",
        "author_name": "Sophie Martin",
        "created_at": "2026-01-20T14:30:00+09:00",
        "content": "Quick announcement: We're hiring a Senior Frontend Engineer! If you know anyone who'd be a good fit, the job posting is live on our careers page. Referral bonus applies 💰",
        "attachments": [],
        "links": ["https://ourcompany.com/careers/senior-frontend"]
    },
    {
        "message_id": "msg-2026-01-20-208",
        "channel_id": "c-general",
        "channel_name": "general",
        "author_id": "u-017",
        "author_name": "Ryan O'Brien",
        "created_at": "2026-01-20T16:30:00+09:00",
        "content": "WFH today working on the API documentation. Taking a break in an hour if anyone wants to hop on a quick call about the new endpoint structure.",
        "attachments": [],
        "links": []
    },
]

def save_fixture(messages, date, filename):
    """Save messages to JSONL fixture file."""
    fixture_path = Path("fixtures") / filename
    fixture_path.parent.mkdir(parents=True, exist_ok=True)

    with open(fixture_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    print(f"✓ Created {fixture_path} with {len(messages)} messages")
    return fixture_path

if __name__ == "__main__":
    # Save the realistic fixture
    save_fixture(MESSAGES_2026_01_20, "2026-01-20", "realistic_2026-01-20.jsonl")
    print("\nRun the pipeline with:")
    print("  python -m src.app ingest --fixture fixtures/realistic_2026-01-20.jsonl --reset")
    print("  python -m src.app run --date 2026-01-20")
