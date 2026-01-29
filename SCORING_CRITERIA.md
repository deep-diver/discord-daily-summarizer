# Scoring Criteria (Generated from spec.md)

## CRITICAL SCORING RULES

### Rule 1: Forced Distribution (Relative Ranking)
For EACH iteration, you MUST rank all 10 variants and assign scores following this distribution:
- **2 variants**: 8-10/10 (excellent) - The best of this iteration
- **3 variants**: 5-7/10 (average) - Middle tier
- **5 variants**: 0-4/10 (below average) - Worst performers

This ensures real differentiation between variants. NO clustering allowed!

### Rule 2: Critical Failure = Automatic Score Cap
If ANY of these critical failures occur, the score is CAPPED regardless of other criteria:
- **Doesn't run at all** (syntax errors, import errors) → Maximum 2/10
- **Crashes on valid input** → Maximum 4/10
- **Missing >20% of features** → Maximum 5/10
- **No tests provided** → Maximum 3/10
- **Security vulnerability** (SQL injection, XSS, etc.) → Maximum 4/10
- **Data loss/corruption** → Maximum 3/10
- **SQLite not used** → Maximum 2/10 (SQLite is required)
- **Discord SDK used in Phase 1** → Maximum 3/10 (Phase 1 must be Discord-free)

Check critical failures FIRST, then score normally with the cap applied.

### Rule 3: Evidence Required
For scores above 7/10 on any criterion, you must provide:
- 2+ specific pieces of evidence (code quotes, test output, logs)
- Explanation of why it deserves this high score

No evidence = max 7/10 for that criterion.

### Rule 4: Differential Scoring (For Iteration 2+)
For iterations after the first, you MUST use differential scoring:

1. **Start with base**: Read the previous best variant's detailed SCORE.md
2. **List EVERY change**: For the new variant, list all differences from the base:
   - What code was added?
   - What code was removed?
   - What code was modified?
   - What architecture changed?
   - What features changed?

3. **Score each change**: For each difference, determine its impact:
   ```
   Change: "Added feature X"
   Impact on criterion Y: +Z points (or -Z points)
   Evidence: [why this change merits the score change]
   ```

4. **Calculate new score**:
   ```
   Base Score: X.X/10 (from previous best)
   + Sum of all positive changes
   - Sum of all negative changes
   = New Score: Y.Y/10
   ```

5. **Document in SCORE.md**:
   ```markdown
   ## Differential Scoring (from iter_N/vXX)

   ### Base Score: X.X/10

   ### Changes Made
   1. [Change 1]
      - Impact: +0.3 on criterion Y (was 7/10, now 7.3/10)
      - Evidence: [specific evidence]

   2. [Change 2]
      - Impact: -0.5 on criterion Z (was 8/10, now 7.5/10)
      - Evidence: [specific evidence]

   ### Score Calculation
   Base: X.X/10
   + 0.3 (Change 1)
   - 0.5 (Change 2)
   + ...
   = Y.Y/10
   ```

This prevents arbitrary scoring and ensures each point change is justified by actual code changes.

## Criteria

### 1. Functional Correctness (35 points total)

#### 1.1 SQLite Persistence (7 points)
- Messages are correctly stored in SQLite database
- All required tables exist: messages, daily_channel_state, daily_channel_delta, global_digest
- Proper indexes on (channel_id, created_at) and (channel_name, created_at)
- JSON fields correctly serialized/deserialized

**Scoring:**
- 10/10: All tables, indexes, and JSON handling perfect
- 8-9: Minor issues (e.g., missing one index, JSON works but not elegant)
- 6-7: Tables exist but indexes missing or JSON has bugs
- 4-5: Major issues (missing tables, broken schema)
- 0-3: Doesn't work at all

**Evidence required:** Database schema output, INSERT/SELECT test results

#### 1.2 Time Window Handling (6 points)
- `--date YYYY-MM-DD` works correctly (00:00:00 to 23:59:59 KST)
- `--start --end` processes multiple days sequentially
- `--last-hours N` handles rolling windows correctly
- Timezone is Asia/Seoul by default

**Scoring:**
- 10/10: All three modes work perfectly with correct timezone
- 8-9: All modes work but minor timezone edge case issues
- 6-7: 2/3 modes work, or timezone issues
- 4-5: Only 1 mode works
- 0-3: Time windows broken

**Evidence required:** Test output for each mode, timestamp validation

#### 1.3 Daily Channel State Generation (7 points)
- LLM generates valid JSON matching DailyChannelState schema exactly
- All required fields present: channel_name, date, topics, progress, artifacts, questions, help_requests, next_steps
- Empty arrays used instead of omitting keys
- No hallucinated claims (state faithful to messages)

**Scoring:**
- 10/10: Perfect schema compliance, no hallucinations
- 8-9: Minor schema deviations (e.g., extra fields)
- 6-7: Works but hallucinates or omits required fields
- 4-5: Major schema issues, frequent hallucinations
- 0-3: Doesn't work

**Evidence required:** Sample state JSON output, validation log

#### 1.4 Delta Computation (6 points)
- Deltas computed via code-based set differences (not LLM)
- Correctly identifies: new_topics, resolved_topics, finished_now, started_now, new_blockers, resolved_blockers, new_links, new_help_requests
- Handles missing yesterday state gracefully (compared_to = null behavior)
- Delta markdown displays correctly

**Scoring:**
- 10/10: All delta types computed correctly, handles edge cases
- 8-9: Minor issues with one delta type
- 6-7: Basic deltas work but edge cases fail
- 4-5: Only partial delta implementation
- 0-3: Deltas broken

**Evidence required:** Delta output JSON, comparison test results

#### 1.5 Global Digest Generation (5 points)
- Rolls up highlights across channels (top 5)
- Aggregates help requests (top 5)
- Deduplicates and caps links (top 10)
- Markdown rendering is correct

**Scoring:**
- 10/10: All aggregation works perfectly
- 8-9: Minor issues with ranking/deduplication
- 6-7: Basic aggregation works but missing features
- 4-5: Partial implementation
- 0-3: Doesn't work

**Evidence required:** Digest output, aggregation test results

#### 1.6 CLI Commands (4 points)
- `ingest`: Works with --fixture, --db, --append/--reset
- `run`: Works with all window modes, --dry-run, --channels, --mock
- `preview`: Displays single channel summary
- `selftest`: Validates full pipeline

**Scoring:**
- 10/10: All commands work perfectly
- 8-9: Minor issues with flags
- 6-7: Most commands work, some missing features
- 4-5: Only basic functionality
- 0-3: Commands broken

**Evidence required:** CLI help output, command execution results

### 2. Code Quality (25 points total)

#### 2.1 Architecture Quality (7 points)
- Clear separation: core/ (business logic), infra/ (infrastructure), app/ (CLI)
- Event-driven architecture implemented
- Dependency injection used (no globals)
- Pure functions for core logic (testable)

**Scoring:**
- 10/10: Perfect architecture, EDA implemented correctly
- 8-9: Good architecture with minor issues
- 6-7: Decent but some coupling issues
- 4-5: Poor organization
- 0-3: No architecture

**Evidence required:** Directory structure, code samples

#### 2.2 Code Organization (6 points)
- Recommended layout followed: src/app, src/core, src/infra, fixtures, tests, data
- Each module has single responsibility
- No code duplication (DRY principle)
- Functions are reasonably sized and focused

**Scoring:**
- 10/10: Perfect organization, no duplication
- 8-9: Good organization, minor duplication
- 6-7: Acceptable but some issues
- 4-5: Poor organization
- 0-3: Chaotic

**Evidence required:** File listing, code samples

#### 2.3 Pydantic Schemas (6 points)
- All data models use Pydantic BaseModel
- Field(default_factory=list) for mutable defaults
- Proper JSON serialization/deserialization
- Type validation working

**Scoring:**
- 10/10: All models use Pydantic correctly
- 8-9: Minor issues
- 6-7: Basic Pydantic usage
- 4-5: Inconsistent usage
- 0-3: Not using Pydantic or broken

**Evidence required:** Model definitions, validation tests

#### 2.4 Documentation (3 points)
- README with Quick Start commands
- Docstrings on key functions
- Inline comments for complex logic
- Type hints used

**Scoring:**
- 10/10: Well-documented throughout
- 8-9: Good documentation
- 6-7: Basic documentation
- 4-5: Minimal docs
- 0-3: No documentation

**Evidence required:** README content, code samples

#### 2.5 Best Practices (3 points)
- Parameterized SQL queries (no injection risk)
- Context managers for resources
- Error handling with clear messages
- Logging implemented

**Scoring:**
- 10/10: All best practices followed
- 8-9: Most practices followed
- 6-7: Basic practices
- 4-5: Security issues
- 0-3: Dangerous code

**Evidence required:** Code samples showing practices

### 3. Robustness & Reliability (20 points total)

#### 3.1 Error Handling (7 points)
- Graceful handling of missing GLM_API_KEY
- Database errors handled (not crashing)
- Invalid input validated with clear errors
- Network errors retried with backoff

**Scoring:**
- 10/10: All errors handled gracefully
- 8-9: Most errors handled
- 6-7: Basic error handling
- 4-5: Crashes on some errors
- 0-3: Crashes frequently

**Evidence required:** Error handling tests, error output samples

#### 3.2 Event System Robustness (6 points)
- EventBus implemented with subscribe/publish
- Error isolation in subscribers (one failing doesn't break bus)
- Event history tracking
- Events emitted at all required points

**Scoring:**
- 10/10: Full event system with error isolation
- 8-9: Good event system, minor issues
- 6-7: Basic events, missing error isolation
- 4-5: Partial implementation
- 0-3: Events broken

**Evidence required:** Event tests, event history output

#### 3.3 Resource Management (4 points)
- Database connections properly closed
- Temporary files cleaned up
- No memory leaks (reasonable for CLI tool)
- Context managers used

**Scoring:**
- 10/10: Perfect resource management
- 8-9: Minor issues
- 6-7: Basic management
- 4-5: Resource leaks
- 0-3: Major leaks

**Evidence required:** Code samples, resource tests

#### 3.4 Concurrency Safety (3 points)
- Thread-safe database operations (if applicable)
- No race conditions in event publishing
- Safe for multiple CLI instances

**Scoring:**
- 10/10: Fully thread-safe
- 8-9: Mostly safe
- 6-7: Basic safety
- 4-5: Some race conditions
- 0-3: Not thread-safe

**Evidence required:** Concurrency tests, code analysis

### 4. Performance & Efficiency (5 points total)

#### 4.1 Database Performance (3 points)
- Efficient queries using indexes
- No N+1 query problems
- Batch operations where appropriate

**Scoring:**
- 10/10: Optimal queries
- 8-9: Good performance
- 6-7: Acceptable
- 4-5: Slow queries
- 0-3: Very slow

**Evidence required:** Query analysis, timing results

#### 4.2 LLM Usage Efficiency (2 points)
- Chunking for large message sets
- Reasonable token usage
- No unnecessary API calls

**Scoring:**
- 10/10: Efficient token usage
- 8-9: Good efficiency
- 6-7: Acceptable
- 4-5: Wasteful
- 0-3: Extremely wasteful

**Evidence required:** Token usage logs, chunking code

### 5. Security & Safety (5 points total)

#### 5.1 SQL Injection Prevention (3 points)
- ALL queries use parameterized statements
- No string concatenation for SQL
- Input validation before queries

**Scoring:**
- 10/10: Perfect parameterization
- 8-9: Minor issues
- 6-7: Mostly parameterized
- 4-5: Some concatenation
- 0-3: Injection vulnerabilities

**Evidence required:** Code review of all SQL

#### 5.2 Data Protection (2 points)
- API keys not logged in verbose mode
- Sensitive data handled carefully
- No hardcoded secrets

**Scoring:**
- 10/10: Perfect data protection
- 8-9: Minor issues
- 6-7: Basic protection
- 4-5: Secrets leaked
- 0-3: No protection

**Evidence required:** Log output analysis, code review

### 6. Usability & Experience (10 points total)

#### 6.1 Rich Terminal Output (5 points)
- **CRITICAL**: Progress bars for long operations
- Tables for structured data
- Panels for highlighted information
- Consistent color coding (green/red/yellow/cyan)
- Status indicators (checkmarks, X marks)

**Scoring:**
- 10/10: Beautiful rich output with all elements
- 8-9: Good rich output, minor missing elements
- 6-7: Basic rich output
- 4-5: Minimal formatting
- 0-3: Plain output, no rich library

**Evidence required:** Screenshots or terminal output samples

#### 6.2 CLI UX (3 points)
- Clear help messages
- Intuitive command structure
- Useful error messages
- Good defaults

**Scoring:**
- 10/10: Excellent UX
- 8-9: Good UX
- 6-7: Acceptable
- 4-5: Confusing
- 0-3: Terrible UX

**Evidence required:** Help output, command samples

#### 6.3 Self-Test Command (2 points)
- Validates full pipeline
- Uses temporary database
- Rich table output with PASS/FAIL
- Non-zero exit on failures

**Scoring:**
- 10/10: Perfect selftest implementation
- 8-9: Good selftest
- 6-7: Basic selftest
- 4-5: Limited selftest
- 0-3: No selftest or broken

**Evidence required:** Selftest output, code

## Final Score Calculation
1. Check for critical failures → Apply cap if found
2. Score each criterion individually (0-10)
3. Overall Score = Weighted average of all category scores
4. Apply forced distribution → Adjust if needed to meet ranking requirements
5. Round to 1 decimal place
6. Report: Overall Score: X.X/10

**Weight breakdown:**
- Functional Correctness: 35% (3.5 weight)
- Code Quality: 25% (2.5 weight)
- Robustness & Reliability: 20% (2.0 weight)
- Performance & Efficiency: 5% (0.5 weight)
- Security & Safety: 5% (0.5 weight)
- Usability & Experience: 10% (1.0 weight)

**This SCORING_CRITERIA.md will be used for ALL variants in ALL iterations.**
