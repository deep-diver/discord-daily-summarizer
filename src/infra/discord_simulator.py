"""Discord message simulator for testing the summarizer.

Generates realistic community chat messages with different personas,
activity patterns, and content types. Can post to real Discord or save as JSONL.
"""

import json
import random
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import discord
except ImportError:
    raise ImportError("discord.py is required. Install with: pip install discord.py")

from src.infra.discord_fetcher import post_message_sync


# Personas for community simulation
PERSONAS = {
    "tech_lead": {
        "name": "Sarah",
        "style": "technical",
        "topics": ["code", "bugs", "architecture", "deploy"],
        "phrases": [
            "Just pushed the fix for {topic}",
            "Anyone else seeing issues with {topic}?",
            "The API is finally working correctly",
            "Need to refactor the {module} module",
            "Deployed to prod, fingers crossed 🤞",
            "Code review done, LGTM!",
            "Blocked on the database schema",
        ]
    },
    "helper": {
        "name": "Alex",
        "style": "helpful",
        "topics": ["questions", "guidance", "documentation"],
        "phrases": [
            "Has anyone worked with {tool} before?",
            "I can help with that, check the docs at {url}",
            "Good question! Here's what I found...",
            "You might want to try {solution}",
            "Let me know if you need more help!",
            "The answer is in the README",
        ]
    },
    "casual": {
        "name": "Jordan",
        "style": "casual",
        "topics": ["random", "memes", "chat", "life"],
        "phrases": [
            "Anyone else watching {game} tonight?",
            "This coffee is my lifeblood today ☕",
            "Just got the new {product}, so hyped!",
            "lol that's hilarious 😂",
            "What's everyone up to?",
            "Weekend plans anyone?",
            "Finally finished work for the day",
        ]
    },
    "gamer": {
        "name": "Kai",
        "style": "gaming",
        "topics": ["games", "streaming", "esports"],
        "phrases": [
            "Who's down for some {game}?",
            "Just hit {rank} rank!",
            "That play was insane!",
            "Stream starting in 10 minutes",
            "GG everyone, good games",
            "Anyone want to squad up?",
            "New season drops tomorrow!",
        ]
    },
    "newbie": {
        "name": "Taylor",
        "style": "learning",
        "topics": ["learning", "questions", "confusion"],
        "phrases": [
            "How do I use {feature} again?",
            "Sorry, still learning the ropes",
            "Can someone explain {topic}?",
            "Thanks for the help everyone!",
            "I think I'm getting the hang of it",
            "One more question...",
        ]
    },
    "enthusiast": {
        "name": "Riley",
        "style": "excited",
        "topics": ["ideas", "features", "suggestions"],
        "phrases": [
            "What if we added {feature}?",
            "Ooh ooh! I have an idea!",
            "This is going to be amazing!",
            "Can we also implement {idea}?",
            "Love this community! 💖",
            "So excited for the upcoming release!",
            "Has anyone considered {approach}?",
        ]
    },
}

# Topic templates for variety
TOPIC_TEMPLATES = {
    "tech": [
        ("authentication", "JWT tokens"),
        ("database", "PostgreSQL optimization"),
        ("API", "REST endpoint design"),
        ("frontend", "React performance"),
        ("backend", "microservices architecture"),
        ("devops", "Docker containers"),
        ("testing", "unit test coverage"),
        ("deployment", "CI/CD pipeline"),
    ],
    "casual": [
        ("lunch", "ordering food"),
        ("weekend", "plans for Saturday"),
        ("music", "new album drops"),
        ("movies", "watching tonight"),
        ("weather", "so hot today"),
        ("coffee", "need more caffeine"),
        ("pets", "my cat did something funny"),
        ("gaming", "late night gaming"),
    ],
    "community": [
        ("events", "community meetup"),
        ("rules", "server guidelines"),
        ("introductions", "new member here"),
        ("help", "looking for advice"),
        ("showcase", "check out my project"),
        ("discussion", "thoughts on this topic"),
    ],
}

# URLs that might be shared
URLS = [
    "https://github.com/discord/discord-api-docs",
    "https://stackoverflow.com/questions/12345",
    "https://docs.python.org/3/library/",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://xkcd.com/2347/",
    "https://github.com/your-org/cool-project",
]


class DiscordSimulator:
    """Simulate realistic Discord community activity."""

    def __init__(
        self,
        guild_id: str,
        channel_id: str,
        token: Optional[str] = None,
    ):
        """Initialize the simulator.

        Args:
            guild_id: Discord server ID
            channel_id: Channel to simulate in
            token: Discord bot token (if posting, else None for JSONL only)
        """
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.token = token
        self.messages = []

    def generate_message(
        self,
        persona_key: str,
        timestamp: datetime,
        reply_to: Optional[str] = None,
    ) -> dict:
        """Generate a simulated Discord message.

        Args:
            persona_key: Key from PERSONAS dict
            timestamp: Message timestamp
            reply_to: Optional message ID this replies to

        Returns:
            Dict in Discord API format
        """
        persona = PERSONAS[persona_key]
        name = persona["name"]
        style = persona["style"]
        phrases = persona["phrases"]

        # Select a random phrase and customize it
        template = random.choice(phrases)

        # Build all possible replacement values
        replacements = {
            # Technical
            "topic": random.choice(random.choice(TOPIC_TEMPLATES["tech"])),
            "module": random.choice(["auth", "database", "api", "frontend"]),
            # Casual
            "game": random.choice(["Valorant", "League", "Apex", "Minecraft", "Overwatch"]),
            "product": random.choice(["iPhone", "AirPods", "PS5", "Switch", "MacBook"]),
            # Helpful
            "tool": random.choice(["Python", "JavaScript", "Docker", "Git", "VS Code"]),
            "url": random.choice(URLS),
            "solution": random.choice(["restarting", "clearing cache", "checking logs", "updating deps"]),
            # Gaming
            "rank": random.choice(["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ascendant", "Immortal"]),
            # Learning/Excited
            "feature": random.choice(["dark mode", "notifications", "search", "API", "dashboard"]),
            "idea": random.choice(["movie night", "game session", "hackathon", "community event", "showcase"]),
            "approach": random.choice(["this approach", "that method", "the standard way", "the new way"]),
            # Generic
            "thing": random.choice(["feature", "tool", "idea", "update"]),
        }

        try:
            content = template.format(**replacements)
        except KeyError as e:
            # If template has unexpected placeholder, use it as-is
            content = template

        # Occasionally add a URL or mention
        if random.random() < 0.3:  # 30% chance
            if random.random() < 0.5:
                content += f" {random.choice(URLS)}"
            else:
                content += f" @random"

        # Build Discord message structure
        msg = {
            "id": str(random.randint(100000000000000000, 999999999999999999)),
            "type": 0,
            "content": content,
            "channel_id": self.channel_id,
            "author": {
                "id": str(random.randint(100000000000000000, 999999999999999999)),
                "username": name.lower().replace(" ", "_"),
                "global_name": name,
                "discriminator": f"{random.randint(1000, 9999)}",
                "bot": False,
                "avatar": None,
            },
            "timestamp": timestamp.isoformat(),
            "edited_timestamp": None,
            "attachments": [],
            "embeds": [],
            "reactions": [],
            "message_reference": {"message_id": reply_to} if reply_to else None,
            "guild_id": self.guild_id,
            "mentions": [],
            "mention_roles": [],
            "pinned": False,
        }

        return msg

    def simulate_day(
        self,
        date: datetime,
        messages_per_day: int = 20,
        activity_pattern: str = "normal",
    ) -> list[dict]:
        """Simulate one day of messages.

        Args:
            date: Date to simulate
            messages_per_day: Approximate number of messages
            activity_pattern: "normal", "bursty", or "quiet"

        Returns:
            List of generated messages
        """
        day_messages = []

        # Define activity hours (9 AM to 11 PM)
        start_hour = 9
        end_hour = 23

        if activity_pattern == "normal":
            # Evenly distributed throughout the day
            for _ in range(messages_per_day):
                hour = random.randint(start_hour, end_hour)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                timestamp = date.replace(
                    hour=hour, minute=minute, second=second,
                    microsecond=random.randint(0, 999999)
                )

                persona = random.choice(list(PERSONAS.keys()))
                reply_chance = 0.2 if day_messages else 0
                reply_to = random.choice(day_messages[-3:])["id"] if (
                    day_messages and random.random() < reply_chance
                ) else None

                msg = self.generate_message(persona, timestamp, reply_to)
                msg["_channel_name"] = f"simulated-{date.strftime('%Y-%m-%d')}"
                day_messages.append(msg)

        elif activity_pattern == "bursty":
            # Bursts of activity separated by quiet periods
            num_bursts = random.randint(3, 6)
            for _ in range(num_bursts):
                burst_start = random.randint(start_hour, end_hour - 2)
                burst_size = random.randint(3, 8)

                for i in range(burst_size):
                    offset_minutes = random.randint(0, 59)
                    timestamp = date.replace(
                        hour=burst_start,
                        minute=offset_minutes,
                        second=random.randint(0, 59),
                        microsecond=random.randint(0, 999999)
                    )

                    persona = random.choice(list(PERSONAS.keys()))
                    msg = self.generate_message(persona, timestamp)
                    msg["_channel_name"] = f"simulated-{date.strftime('%Y-%m-%d')}"
                    day_messages.append(msg)

        elif activity_pattern == "quiet":
            # Few messages, mostly in evening
            for _ in range(messages_per_day // 3):
                hour = random.randint(18, end_hour)
                timestamp = date.replace(
                    hour=hour,
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                    microsecond=random.randint(0, 999999)
                )

                persona = random.choice(list(PERSONAS.keys()))
                msg = self.generate_message(persona, timestamp)
                msg["_channel_name"] = f"simulated-{date.strftime('%Y-%m-%d')}"
                day_messages.append(msg)

        # Sort by timestamp
        day_messages.sort(key=lambda m: m["timestamp"])

        return day_messages

    def simulate_days(
        self,
        start_date: datetime,
        num_days: int,
        messages_per_day: int = 20,
        activity_pattern: str = "normal",
        output_file: Optional[str] = None,
    ) -> list[dict]:
        """Simulate multiple days of messages.

        Args:
            start_date: First day to simulate
            num_days: Number of days to simulate
            messages_per_day: Messages per day (approximate)
            activity_pattern: "normal", "bursty", or "quiet"
            output_file: Optional JSONL file to save to

        Returns:
            All generated messages
        """
        all_messages = []

        for day_num in range(num_days):
            current_date = start_date + timedelta(days=day_num)
            day_messages = self.simulate_day(
                current_date, messages_per_day, activity_pattern
            )
            all_messages.extend(day_messages)
            print(f"✓ Generated {len(day_messages)} messages for {current_date.strftime('%Y-%m-%d')}")

        if output_file:
            self.save_to_jsonl(all_messages, output_file)
            print(f"✓ Saved {len(all_messages)} messages to {output_file}")

        return all_messages

    def save_to_jsonl(self, messages: list[dict], output_file: str):
        """Save messages to JSONL file.

        Args:
            messages: List of message dicts
            output_file: Path to output file
        """
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    async def post_to_discord(
        self,
        messages: list[dict],
        delay_range: tuple = (1, 5),
    ):
        """Post simulated messages to Discord.

        Args:
            messages: List of message dicts to post
            delay_range: Min/max seconds between posts
        """
        intents = discord.Intents(
            guilds=True,
            messages=True,
            message_content=True,
        )

        client = discord.Client(intents=intents)
        posted = [0]

        @client.event
        async def on_ready():
            """Called when the bot is ready."""
            try:
                channel = client.get_channel(int(self.channel_id))
                if not channel:
                    print(f"✗ Channel {self.channel_id} not found")
                    await client.close()
                    return

                print(f"📝 Posting {len(messages)} messages to #{channel.name}...")

                for i, msg in enumerate(messages):
                    try:
                        await channel.send(msg["content"])
                        posted[0] += 1

                        if i % 5 == 0:
                            print(f"  Posted {i+1}/{len(messages)} messages...")

                        # Random delay between messages
                        delay = random.uniform(*delay_range)
                        await asyncio.sleep(delay)

                    except Exception as e:
                        print(f"✗ Error posting message {i+1}: {e}")

                print(f"✓ Posted {posted[0]} messages to #{channel.name}")

            finally:
                await client.close()

        await client.start(self.token)
        return posted[0]


def post_messages_sync(
    messages: list[dict],
    token: str,
    channel_id: str,
    delay_range: tuple = (1, 5),
) -> int:
    """Synchronous wrapper for posting messages to Discord.

    Args:
        messages: List of message dicts to post
        token: Discord bot token
        channel_id: Channel ID to post to
        delay_range: Min/max seconds between posts

    Returns:
        Number of messages posted
    """
    simulator = DiscordSimulator(guild_id="0", channel_id=channel_id)

    async def _post():
        return await simulator.post_to_discord(messages, delay_range)

    return asyncio.run(_post())


def simulate_community_activity(
    guild_id: str,
    channel_id: str,
    start_date: datetime,
    num_days: int,
    messages_per_day: int = 20,
    activity_pattern: str = "normal",
    output_file: str = "simulated_messages.jsonl",
) -> list[dict]:
    """Simulate community activity and save to JSONL.

    Args:
        guild_id: Discord server ID
        channel_id: Channel to simulate
        start_date: First day to simulate
        num_days: Number of days
        messages_per_day: Messages per day
        activity_pattern: "normal", "bursty", or "quiet"
        output_file: Output JSONL file

    Returns:
        Generated messages

    Example:
        >>> from datetime import datetime, timedelta
        >>> messages = simulate_community_activity(
        ...     guild_id="123456789",
        ...     channel_id="987654321",
        ...     start_date=datetime.now() - timedelta(days=3),
        ...     num_days=3,
        ...     messages_per_day=25,
        ...     activity_pattern="normal",
        ... )
        >>> print(f"Generated {len(messages)} messages")
    """
    simulator = DiscordSimulator(guild_id, channel_id)
    return simulator.simulate_days(
        start_date=start_date,
        num_days=num_days,
        messages_per_day=messages_per_day,
        activity_pattern=activity_pattern,
        output_file=output_file,
    )
