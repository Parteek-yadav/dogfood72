# Dogfood 2026 - Data Model & Schema Specification

This document details the relational data schema, model definitions, constraints, and data import/export pathways for the Dogfood 2026 hackathon portal.

---

## 1. Relational Entity Diagram (ER Overview)

```
┌─────────────────────────────────┐
│           auth.User             │
└───────┬─────────────────┬───────┘
        │ 1:1             │ 1:N
        ▼                 ├──────────────────────────┐
┌──────────────┐          ▼                          ▼
│   Profile    │   ┌──────────────┐           ┌──────────────┐
└──────────────┘   │  EventRole   │           │     Team     │
                   └──────┬───────┘           └──────┬───────┘
                          │ N:1                      │ 1:N
                          ▼                          ├─────────────────────────┐
                   ┌──────────────┐                  ▼                         ▼
                   │    Event     │           ┌──────────────┐          ┌──────────────┐
                   └───┬───┬───┬──┘           │TeamMembership│          │    Invite    │
           ┌───────────┘   │   └──────────┐   └──────────────┘          └──────────────┘
           ▼               ▼              ▼
    ┌──────────────┐┌──────────────┐┌──────────────┐
    │    Track     ││    Prize     ││CustomQuestion│
    └──────┬───────┘└──────────────┘└──────────────┘
           │ N:1                                      ┌────────────────────────┐
           ▼                                          │       Submission       │
    ┌─────────────────────────────────────────────────┴───────────┬────────────┘
    │                                                             │ 1:N
    ├─────────────────────────────┬───────────────────────────────┤
    ▼                             ▼                               ▼
┌──────────────┐           ┌──────────────┐                ┌──────────────┐
│SubmissionImg │           │SubmissionVer │                │JudgeAssignmt │
└──────────────┘           └──────────────┘                └──────┬───────┘
                                                                  │ 1:N
┌──────────────┐           ┌──────────────┐                       ▼
│    Rubric    │◄──────────┤RubricCriter. │                ┌──────────────┐
└──────────────┘ 1:N       └──────┬───────┘                │    Score     │
                                  │ N:1                    └──────────────┘
                                  └───────────────────────────────┘
┌──────────────┐
│NormalizedSc. │◄── (Stores z-score normalized output per Submission)
└──────────────┘
┌──────────────┐
│     Vote     │◄── (Dual-constraint: authenticated User OR signed anonymous voter_token)
└──────────────┘
┌──────────────┐
│   Comment    │◄── (Participant feedback on Submission)
└──────────────┘
┌──────────────┐
│AuditLogEntry │◄── (Immutable platform activity and security audit trail)
└──────────────┘
```

---

## 2. Model Definitions & Constraints

### 2.1 Accounts & Identity (`accounts`)

#### `Profile`
- **Purpose**: Extends Django's `auth.User` model (1:1 relationship) for platform-level identity.
- **Fields**:
  - `user`: `OneToOneField(User, on_delete=CASCADE, related_name='profile')`
  - `bio`: `TextField(blank=True)`
  - `avatar`: `ImageField(upload_to='profiles/avatars/', blank=True, null=True)`
  - `github_handle`: `CharField(max_length=100, blank=True)`
  - `linkedin_url`: `URLField(blank=True)`
  - `website_url`: `URLField(blank=True)`
  - `created_at`, `updated_at`: `DateTimeField`

---

### 2.2 Event Management (`events`)

#### `Event`
- **Purpose**: Primary hackathon entity defining timelines and publication state.
- **Fields**:
  - `name`: `CharField(max_length=255)`
  - `slug`: `SlugField(max_length=255, unique=True, db_index=True)`
  - `description`: `TextField`
  - `start_date`: `DateTimeField`
  - `end_date`: `DateTimeField`
  - `submission_deadline`: `DateTimeField` (Hard deadline for submission edits)
  - `voting_start`: `DateTimeField` (Start of evaluation period)
  - `voting_end`: `DateTimeField` (End of evaluation/judging period)
  - `is_published`: `BooleanField(default=False, db_index=True)`
  - `organizer`: `ForeignKey(User, on_delete=PROTECT, related_name='organized_events')`
  - `created_at`, `updated_at`: `DateTimeField`
- **Constraints & Validation**:
  - `clean()` enforces `start_date < end_date` and `voting_start < voting_end`.
  - Indexes on `['slug']`, `['is_published', 'submission_deadline']`, and `['start_date', 'end_date']`.

#### `EventRole`
- **Purpose**: Grants per-event roles (`ORGANIZER`, `JUDGE`, `PARTICIPANT`) to users. Decoupled from global identity.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='roles')`
  - `user`: `ForeignKey(User, on_delete=CASCADE, related_name='event_roles')`
  - `role`: `CharField(max_length=20, choices=['organizer', 'judge', 'participant'])`
  - `assigned_at`: `DateTimeField(auto_now_add=True)`
- **Constraints**:
  - `UniqueConstraint(fields=['event', 'user', 'role'], name='unique_event_user_role')`.

#### `Track`
- **Purpose**: Challenge categories or tracks within an event.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='tracks')`
  - `name`: `CharField(max_length=255)`
  - `description`: `TextField(blank=True)`
- **Constraints**:
  - `UniqueConstraint(fields=['event', 'name'], name='unique_event_track_name')`.

#### `Prize`
- **Purpose**: Awards offered for the event, optionally track-specific.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='prizes')`
  - `track`: `ForeignKey(Track, on_delete=SET_NULL, null=True, blank=True)`
  - `name`: `CharField(max_length=255)`
  - `amount`: `CharField(max_length=255, blank=True)`
  - `description`: `TextField(blank=True)`
  - `rank`: `PositiveIntegerField(default=1)`

#### `CustomQuestion`
- **Purpose**: Organizer-defined typed custom questions for project submissions.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='custom_questions')`
  - `label`: `CharField(max_length=255)`
  - `field_type`: `CharField(choices=['text', 'textarea', 'url', 'select', 'checkbox'])`
  - `required`: `BooleanField(default=False)`
  - `order`: `PositiveIntegerField(default=0)`
  - `choices`: `JSONField(default=list, blank=True)` (Non-empty list required if `field_type == 'select'`)

---

### 2.3 Teams & Invitations (`teams`)

#### `Team`
- **Purpose**: Participating group in an event.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='teams')`
  - `name`: `CharField(max_length=255)`
  - `created_by`: `ForeignKey(User, on_delete=PROTECT, related_name='created_teams')`
  - `created_at`, `updated_at`: `DateTimeField`
- **Constraints**:
  - `UniqueConstraint(fields=['event', 'name'], name='unique_event_team_name')`.

#### `TeamMembership`
- **Purpose**: User participation on a team.
- **Fields**:
  - `team`: `ForeignKey(Team, on_delete=CASCADE, related_name='memberships')`
  - `user`: `ForeignKey(User, on_delete=CASCADE, related_name='team_memberships')`
  - `role`: `CharField(choices=['leader', 'member'], default='member')`
  - `joined_at`: `DateTimeField(auto_now_add=True)`
- **Constraints**:
  - `UniqueConstraint(fields=['team', 'user'], name='unique_team_user_membership')`.
  - Application logic prevents a user from holding memberships in multiple teams within the same event.

#### `Invite`
- **Purpose**: Single-use tokenized invite to join a team.
- **Fields**:
  - `team`: `ForeignKey(Team, on_delete=CASCADE, related_name='invites')`
  - `token`: `CharField(max_length=64, unique=True, default=secrets.token_urlsafe(32))`
  - `created_by`: `ForeignKey(User, on_delete=PROTECT)`
  - `email`: `EmailField(blank=True, null=True)` (Optional email gating)
  - `expires_at`: `DateTimeField`
  - `used_at`: `DateTimeField(null=True, blank=True)`
  - `created_at`: `DateTimeField(auto_now_add=True)`
- **Validation**:
  - `is_valid()` returns `True` only if `used_at IS NULL` and `now() < expires_at`. Once used, `used_at` is stamped.

---

### 2.4 Submissions & Versions (`submissions`)

#### `Submission`
- **Purpose**: The project submitted by a team.
- **Fields**:
  - `team`: `ForeignKey(Team, on_delete=CASCADE, related_name='submissions')`
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='submissions')`
  - `track`: `ForeignKey(Track, on_delete=SET_NULL, null=True, blank=True)`
  - `title`: `CharField(max_length=255)`
  - `tagline`: `CharField(max_length=255, blank=True)`
  - `description`: `TextField` (Markdown format)
  - `thumbnail`: `ImageField(upload_to='submissions/thumbnails/', blank=True, null=True)`
  - `repo_url`: `URLField(blank=True)`
  - `live_url`: `URLField(blank=True)`
  - `demo_video_url`: `URLField(blank=True)`
  - `tech_tags`: `JSONField(default=list, blank=True)` (e.g. `["Python", "Django", "Docker"]`)
  - `custom_answers`: `JSONField(default=dict, blank=True)` (Keyed by `str(CustomQuestion.id)`)
  - `status`: `CharField(choices=['draft', 'submitted'], default='draft', db_index=True)`
  - `created_at`, `updated_at`: `DateTimeField`
  - `submitted_at`: `DateTimeField(null=True, blank=True, db_index=True)`
- **Constraints & Two-Tier Deadline Lock**:
  - `UniqueConstraint(fields=['team', 'event'], name='unique_team_event_submission')` (1 submission per team).
  - `clean()` enforces: if updating an existing record and `now() > event.submission_deadline`, raise `ValidationError` and record `submission.deadline_blocked_edit_attempt` to `AuditLogEntry`.
  - `validate_custom_answers()` validates all `custom_answers` entries against `event.custom_questions`.

#### `SubmissionVersion`
- **Purpose**: Immutable sequential snapshot of every submission revision.
- **Fields**:
  - `submission`: `ForeignKey(Submission, on_delete=CASCADE, related_name='versions')`
  - `version_number`: `PositiveIntegerField`
  - `title`: `CharField(max_length=255)`
  - `tagline`: `CharField(max_length=255, blank=True)`
  - `description`: `TextField`
  - `custom_answers`: `JSONField(default=dict)`
  - `status`: `CharField(max_length=20)`
  - `created_by`: `ForeignKey(User, on_delete=SET_NULL, null=True, blank=True)`
  - `created_at`: `DateTimeField(auto_now_add=True)`
- **Constraints**:
  - `UniqueConstraint(fields=['submission', 'version_number'], name='unique_submission_version')`.

#### `SubmissionImage`
- **Purpose**: Supporting screenshots and diagrams for public gallery carousels.
- **Fields**:
  - `submission`: `ForeignKey(Submission, on_delete=CASCADE, related_name='gallery_images')`
  - `image`: `ImageField(upload_to='submissions/gallery/')`
  - `caption`: `CharField(max_length=255, blank=True)`
  - `order`: `PositiveIntegerField(default=0)`

---

### 2.5 Judging & Normalization (`judging`)

#### `Rubric` & `RubricCriterion`
- **Purpose**: Weighted scoring framework.
- **Fields (`Rubric`)**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='rubrics')`
  - `name`: `CharField(max_length=255)`
  - `description`: `TextField(blank=True)`
- **Fields (`RubricCriterion`)**:
  - `rubric`: `ForeignKey(Rubric, on_delete=CASCADE, related_name='criteria')`
  - `name`: `CharField(max_length=255)`
  - `description`: `TextField(blank=True)`
  - `weight`: `DecimalField(max_digits=5, decimal_places=2, default=25.00)` (Target percentage)
  - `order`: `PositiveIntegerField(default=0)`
- **Validation**:
  - `rubric.validate_weight_sum()` verifies criteria weights sum to 100.00%.

#### `JudgeAssignment`
- **Purpose**: Maps a Judge to a Submission for evaluation.
- **Fields**:
  - `event`: `ForeignKey(Event, on_delete=CASCADE, related_name='judge_assignments')`
  - `judge`: `ForeignKey(User, on_delete=CASCADE, related_name='judging_assignments')`
  - `submission`: `ForeignKey(Submission, on_delete=CASCADE, related_name='judge_assignments')`
  - `status`: `CharField(choices=['assigned', 'in_progress', 'completed'], default='assigned')`
  - `assigned_at`: `DateTimeField(auto_now_add=True)`
  - `completed_at`: `DateTimeField(null=True, blank=True)`
- **Constraints**:
  - `UniqueConstraint(fields=['judge', 'submission'], name='unique_judge_submission_assignment')`.

#### `Score`
- **Purpose**: Evaluator rating on a single criterion for an assignment.
- **Fields**:
  - `assignment`: `ForeignKey(JudgeAssignment, on_delete=CASCADE, related_name='scores')`
  - `criterion`: `ForeignKey(RubricCriterion, on_delete=CASCADE, related_name='scores')`
  - `value`: `PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])`
  - `feedback`: `TextField(blank=True)`
  - `created_at`, `updated_at`: `DateTimeField`
- **Constraints**:
  - `UniqueConstraint(fields=['assignment', 'criterion'], name='unique_assignment_criterion_score')`.

#### `NormalizedScore`
- **Purpose**: Persisted output of cross-judge z-score standardization.
- **Fields**:
  - `submission`: `ForeignKey(Submission, on_delete=CASCADE, related_name='normalized_scores')`
  - `method`: `CharField(max_length=50, default='zscore')`
  - `raw_mean`: `DecimalField(max_digits=6, decimal_places=3)`
  - `normalized_value`: `DecimalField(max_digits=6, decimal_places=3)`
  - `computed_at`: `DateTimeField(auto_now=True)`
  - `metadata`: `JSONField(default=dict, blank=True)` (Stores judge counts, sample variances, and z-score lists)
- **Constraints**:
  - `UniqueConstraint(fields=['submission', 'method'], name='unique_submission_normalization_method')`.

---

### 2.6 Voting & Audit (`voting` & `core`)

#### `Vote`
- **Purpose**: Dual-constraint community voting model.
- **Fields**:
  - `submission`: `ForeignKey(Submission, on_delete=CASCADE, related_name='votes')`
  - `user`: `ForeignKey(User, null=True, blank=True)`
  - `voter_token`: `CharField(max_length=64, null=True, blank=True)`
  - `weight`: `DecimalField(max_digits=6, decimal_places=2, default=1.00)`
  - `ip_hash`: `CharField(max_length=64, blank=True)`
- **Dual Unique Constraints**:
  - Authenticated: `(submission, user) WHERE user IS NOT NULL`
  - Anonymous: `(submission, voter_token) WHERE voter_token IS NOT NULL`

#### `AuditLogEntry`
- **Purpose**: Immutable activity and security logging.
- **Fields**:
  - `actor`: `ForeignKey(User, on_delete=SET_NULL, null=True, blank=True)`
  - `action`: `CharField(max_length=100, db_index=True)`
  - `target_type`: `CharField(max_length=100, db_index=True)`
  - `target_id`: `CharField(max_length=100, db_index=True)`
  - `metadata`: `JSONField(default=dict, blank=True)`
  - `created_at`: `DateTimeField(auto_now_add=True, db_index=True)`

---

## 3. Data Import Pathways

### 3.1 Initial Seeding (`seed_fixtures`)
The management command `python manage.py seed_fixtures` operates idempotently:
1. **JSON Fixture Loading**:
   - Inspects the repository root for `fixtures.json`.
   - If found, loads the official organizer specification format:
     ```json
     {
       "event": {
         "id": "evt_01",
         "name": "Dogfood 2026 Invitational",
         "submissions_close": "2026-09-27T10:00:00Z",
         "tracks": ["AI Agents", "Tooling"]
       },
       "judges": [...],
       "teams": [...],
       "projects": [...]
     }
     ```
2. **Built-in Specification Seeding**:
   - When no `fixtures.json` is provided, seeds event `evt_01` with:
     - 4 checker accounts: `organizer`, `judge_a`, `judge_b`, `participant`.
     - Pre-created Django sessions with fixed keys (`session_organizer_key`, etc.).
     - 30 judges, 40 submitted projects across 3 tracks, and 120 assignments.
     - Rubric with weighted criteria and scores including deliberate edge cases (zero-variance judge, in-progress review batches, duplicate project entry).
3. **Idempotence**:
   - Uses `get_or_create` and `update_or_create` across all models. Re-running `seed_fixtures` updates existing entities without generating duplicate rows.

### 3.2 Standard Django Fixtures
Standard Django JSON fixtures can be loaded directly:
```bash
docker compose exec web python manage.py loaddata <fixture_file.json>
```

---

## 4. Data Export Pathways (Platform Exit Strategy)

An organizer wishing to extract all data or leave the platform has four supported pathways:

### Pathway 1: Web CSV Exports (Instant Dashboard Downloads)

| Export Dataset | Route | Access | Contents / Columns |
| :--- | :--- | :--- | :--- |
| **All Evaluations (Checker)** | `GET /api/export.csv` | Organizer / Admin | `event_slug`, `submission_id`, `submission_title`, `team_name`, `judge_username`, `criterion`, `score`, `feedback` |
| **Raw Evaluation Scores** | `GET /judging/events/<id>/export/raw-scores/` | Organizer / Admin | `assignment_id`, `submission_id`, `submission_title`, `team_name`, `judge_username`, `criterion_name`, `weight`, `raw_score`, `feedback`, `scored_at` |
| **Normalized Rankings** | `GET /judging/events/<id>/export/normalized-scores/` | Organizer / Admin | `rank`, `submission_id`, `submission_title`, `team_name`, `raw_mean_score`, `normalized_score`, `normalization_method`, `computed_at` |
| **Judge Assignments Roster** | `GET /judging/events/<id>/export/assignments/` | Organizer / Admin | `assignment_id`, `judge_username`, `judge_email`, `submission_id`, `submission_title`, `team_name`, `status`, `assigned_at`, `completed_at` |

### Pathway 2: CLI CSV Export Command (`export_judging_data`)
Export datasets directly to stdout or disk:
```bash
# Export normalized rankings to a local file
docker compose exec web python manage.py export_judging_data --event 1 --dataset normalized_scores --output /app/normalized_rankings.csv

# Export raw scores to stdout
docker compose exec web python manage.py export_judging_data --event 1 --dataset raw_scores
```
Available datasets: `raw_scores`, `normalized_scores`, `judge_assignments`, `final_rankings`.

### Pathway 3: Complete Database Dump (SQL Archive)
To extract the complete relational database (all users, events, submissions, rubrics, scores, audit entries):
```bash
docker compose exec db pg_dump -U dogfood_user -d dogfood > full_platform_backup.sql
```
This produces an open, standard SQL dump that can be restored on any PostgreSQL 16+ instance.

### Pathway 4: Django Serialized JSON Dump (`dumpdata`)
To export all domain models into platform-independent JSON:
```bash
docker compose exec web python manage.py dumpdata events teams submissions judging voting core --indent 2 > platform_data.json
```

### Media Assets Extraction
Project thumbnails and gallery screenshots stored in the Docker media volume can be copied out:
```bash
docker cp dogfood_web:/app/media ./media_archive/
```
