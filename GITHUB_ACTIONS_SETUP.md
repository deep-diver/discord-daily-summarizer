# GitHub Actions Setup Guide

## Step 1: Push Your Code to GitHub

```bash
# Initialize git if not already done
git init
git add .
git commit -m "Add Discord daily summarizer with GitHub Actions"

# Create a new repo on GitHub first, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

## Step 2: Add Secrets to GitHub

Go to: **Your Repository → Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets:

| Secret Name | Value |
|-------------|-------|
| `GLM_API_KEY` | `your-glm-api-key-here` |
| `DISCORD_BOT_TOKEN` | `your-discord-bot-token-here` |
| `DISCORD_GUILD_ID` | `your-server-guild-id` |
| `DISCORD_CHANNEL_IDS` | `channel1,channel2,channel3` |

## Step 3: Enable GitHub Actions

1. Go to **Actions** tab in your repository
2. Click **I understand my workflows, go ahead and enable them**

## Step 4: Test Manually

1. Go to **Actions** tab
2. Click **"Discord Daily Summary"** workflow
3. Click **"Run workflow"** button
4. Select branch and click **"Run workflow"**

## Step 5: Monitor

After it runs, check:
- **Actions** tab to see if it succeeded
- Your Discord channels for the posted summaries

---

## Schedule

The workflow runs **daily at 9 PM KST** (8 AM UTC).

To change the time, edit `.github/workflows/daily-summary.yml`:
```yaml
schedule:
  - cron: '0 8 * * *'  # Format: hour day month day-of-week
                         # 8 AM UTC = 5 PM EST / 9 PM KST
```

## Cron Format Quick Reference

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, Sunday = 0)
│ │ │ │ │
* * * * *
```

Common schedules:
| Time KST | Cron Expression |
|----------|-----------------|
| 9 PM | `0 8 * * *` |
| 10 AM | `0 1 * * *` |
| Midnight | `0 15 * * *` |
| Every 6 hours | `0 */6 * * *` |
