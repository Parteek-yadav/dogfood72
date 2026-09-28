# Dogfood 2026 - System Architecture

This document describes the architectural layout, component interactions, core request flows, and key technical decisions implemented in the Dogfood 2026 hackathon portal.

---

## 1. System Shape & Django Applications

The platform is designed around a modular Django 5 architecture running on Python 3.12 and PostgreSQL 16. Django templates, htmx, and Tailwind CSS provide a responsive server-rendered UI, while Django REST Framework (DRF) and `drf-spectacular` expose role-isolated, OpenAPI-documented REST APIs.

```
                          ┌──────────────────────────┐
                          │   Visitor / Participant  │
                          │   Judge / Organizer UI   │
                          └────────────┬─────────────┘
                                       │ HTTP / htmx / REST
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             portal (Root Routing)                           │
├───────────────┬────────────────┬──────────────────────────┬─────────────────┤
│ accounts      │ events         │ teams                    │ submissions     │
│ User profiles │ Event CRUD     │ Teams & memberships      │ Drafts & edits  │
│ Auth & login  │ Roles & tracks │ Expiring single-use      │ Version history │
│               │ CustomQuestion │ invite tokens            │ Public gallery  │
├───────────────┼────────────────┴──────────────────────────┴─────────────────┤
│ judging       │ - Rubric builder & criterion weighting                      │
│               │ - Balanced K-judge assignment with COI exclusion            │
│               │ - Role-isolated REST APIs (/api/judge/scores, export.csv)   │
│               │ - Cross-judge z-score score normalization                   │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ core          │ - Role permission checks (is_event_organizer, etc.)         │
│               │ - Immutable AuditLogEntry logging utility                   │
│               │ - seed_fixtures management command                          │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ voting        │ - Vote & Comment models (dual-constraint auth/anon)         │
└───────────────┴─────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                         PostgreSQL 16 Database
```

### Application Breakdown

| App | Primary Models | Core Responsibilities |
| :--- | :--- | :--- |
| **`core`** | `AuditLogEntry` | Centralized permission helpers (`is_event_organizer`, `is_event_judge`, `is_team_member`), immutable audit logging, and `seed_fixtures` management command. |
| **`accounts`** | `Profile` | Extends Django's built-in `User` model via OneToOne for global identity (bio, GitHub handle, website). Handles authentication and sessions. |
| **`events`** | `Event`, `EventRole`, `Track`, `Prize`, `CustomQuestion` | Event lifecycle timelines, track categorization, organizer custom question definitions, and per-event user role assignments (`ORGANIZER`, `JUDGE`, `PARTICIPANT`). |
| **`teams`** | `Team`, `TeamMembership`, `Invite` | Team creation, membership tracking, single-team-per-event validation, and random single-use invite tokens (`secrets.token_urlsafe(32)`). |
| **`submissions`** | `Submission`, `SubmissionImage`, `SubmissionVersion` | Project drafts, file uploads, dynamic custom question validation, hard deadline lock, immutable revision snapshots, and public gallery views. |
| **`judging`** | `Rubric`, `RubricCriterion`, `JudgeAssignment`, `Score`, `NormalizedScore` | Weighted rubric builder, pure algorithmic assignment balancer with Conflict of Interest (COI) exclusion, judge scoring, role-isolated DRF APIs, z-score normalization pipeline, and CSV exports. |
| **`voting`** | `Vote`, `Comment` | Community voting schema with dual-constraint validation (authenticated user or signed anonymous token) and submission comments (T3 base models). |

---

## 2. Request Flows: The Two Critical Paths

### Path A: Submission Lifecycle Flow

```
[Participant]
      │
      ├─ 1. Form Team ──────────────────► Team.objects.create(...)
      │                                   EventRole(role='participant')
      │
      ├─ 2. Invite Members ─────────────► Invite.objects.create(token=token_urlsafe)
      │                                   (Single-use, expiring link)
      │
      ├─ 3. Create Draft Submission ────► Submission.objects.create(status='draft')
      │                                   SubmissionVersion.objects.create(v1)
      │                                   AuditLogEntry.log('submission.created')
      │
      ├─ 4. Edit Draft & Answers ───────► Submission.save()
      │                                   ├── clean(): Check submission_deadline
      │                                   │            (If now > deadline: raise ValidationError,
      │                                   │             log 'submission.deadline_blocked_edit_attempt')
      │                                   ├── validate_custom_answers():
      │                                   │   - Verify question IDs belong to event
      │                                   │   - Verify choice values in select fields
      │                                   └── SubmissionVersion.objects.create(vN+1)
      │
      └─ 5. Final Submit ───────────────► Submission.status = 'submitted'
                                          ├── validate_custom_answers(): Enforce required fields
                                          ├── submitted_at = timezone.now()
                                          └── Project appears in Public Gallery (GET /projects)
```

1. **Team Formation & Role Assignment**: A participant creates a team for an event. The system creates a `Team` record, sets the user as `TeamMembership.Role.LEADER`, and assigns `EventRole.Role.PARTICIPANT`.
2. **Member Invitation**: The team leader generates an invite. An `Invite` record is created with a cryptographically random token (`secrets.token_urlsafe(32)`) and an expiration timestamp. When an invitee accepts, the system verifies `invite.is_valid()`, checks that the invitee is not already on another team in this event, marks `invite.used_at = now()`, and creates a `TeamMembership`.
3. **Draft Creation**: The team leader initializes a submission (`POST /submissions/team/<id>/new/`). The submission is created in `status='draft'`. A version record (`SubmissionVersion` v1) is snapshotted, and an `AuditLogEntry` is recorded.
4. **Iterative Edits & Validation**:
   - The team modifies project writeups, tech tags, repository URLs, and answers custom questions (`POST /submissions/<id>/edit/`).
   - `Submission.clean()` checks `event.submission_deadline`. If `now > event.submission_deadline`, the edit is rejected with HTTP 403, and `submission.deadline_blocked_edit_attempt` is logged to `AuditLogEntry`.
   - `validate_custom_answers()` verifies each field against `CustomQuestion` rules (ensuring question IDs belong to the event, values match select choice constraints, and types conform).
   - Each saved edit increments and persists a snapshot in `SubmissionVersion`.
5. **Final Submission**: Setting `status='submitted'` triggers verification of all `required=True` custom questions. The timestamp `submitted_at` is locked, and the project becomes visible in the public gallery (`GET /projects`).

---

### Path B: Judging & Scoring Lifecycle Flow

```
[Organizer]
      │
      ├─ 1. Build Rubric ──────────────► Rubric.objects.create(name=...)
      │                                  RubricCriterion.objects.bulk_create([
      │                                      Criterion(weight=40),
      │                                      Criterion(weight=30),
      │                                      Criterion(weight=30)
      │                                  ]) (Must sum to 100%)
      │
      ├─ 2. Run Assignment Balancer ───► run_event_judge_assignments(event, k=3)
      │                                  ├── Build COI Map (exclude team members & creators)
      │                                  ├── assign_judges(judges, submissions, k, exclusions)
      │                                  └── JudgeAssignment.objects.bulk_create(...)
      │
[Judge]
      │
      ├─ 3. Fetch Assignments ─────────► GET /api/judge/scores (or /my-assignments/)
      │                                  (Returns ONLY this judge's assignments)
      │
      ├─ 4. Submit Scores ─────────────► POST /judging/assignments/<id>/score/
      │                                  ├── Check window: now <= (voting_end or end_date)
      │                                  ├── Score.objects.update_or_create(value=1..5)
      │                                  └── status = 'completed' (when all criteria scored)
      │
[Security Isolation Boundary]
      ├─ Judge B snoops on Judge A ────► GET /api/judge/scores?judge=judge_a
      │                                  └── Returns HTTP 403 Forbidden!
      │
[Organizer]
      │
      ├─ 5. Review Progress ───────────► GET /judging/events/<id>/progress/
      │                                  (Displays real-time completion percentages)
      │
      ├─ 6. Compute Normalization ─────► run_score_normalization(event)
      │                                  ├── Compute judge mean (mu_j) & stddev (sigma_j)
      │                                  ├── Standardize z = (score - mu_j) / sigma_j
      │                                  ├── Rescale to 1–5 scale: grand_mean + (z * grand_std)
      │                                  ├── NormalizedScore.objects.update_or_create(...)
      │                                  └── AuditLogEntry.log('judging.normalization_computed')
      │
      └─ 7. Export Datasets ───────────► GET /api/export.csv
                                         (Raw scores, normalized rankings, CSV body)
```

1. **Rubric Definition**: The organizer creates a `Rubric` with multiple `RubricCriterion` records. Weights represent target percentages summing to 100.00% (validated via `rubric.validate_weight_sum()`).
2. **Algorithmic Assignment**:
   - The organizer executes the assignment balancer (`run_event_judge_assignments`).
   - The system builds a Conflict of Interest (COI) exclusion map: for every submission, all team members and the team creator are added to that submission's exclusion set.
   - The pure function `assign_judges` greedily assigns $K$ eligible judges per submission, prioritizing judges with the lowest current workload, ensuring maximum workload difference between judges never exceeds 1.
3. **Scoring Execution**:
   - The judge navigates to their scoring interface (`/judging/assignments/<id>/score/`).
   - The view verifies that the judging window is open (`now <= event.voting_end or event.end_date`).
   - The judge evaluates each criterion on a 1–5 scale. When all criteria are scored, `assignment.status` is set to `COMPLETED`.
4. **Role Isolation Boundary**:
   - REST API endpoints (`/api/judge/scores`, `/api/submissions/<id>/scores/`, `/api/events/<id>/judge-progress/`) strictly enforce role boundaries.
   - A judge attempting to view another judge's scores or pass `?judge=other_judge` receives HTTP 403 Forbidden.
   - An organizer querying the API receives full multi-judge evaluation visibility.
5. **Score Normalization**:
   - The organizer triggers normalization (`compute_normalization`).
   - For every judge, the system computes their raw mean $\mu_j$ and sample standard deviation $\sigma_j$.
   - Each raw rating is converted to a z-score: $z = \frac{x - \mu_j}{\sigma_j}$ (if $\sigma_j = 0$, $z = 0.0$).
   - Scores are rescaled to the 1–5 range centered at the grand mean: $\text{score}_{\text{norm}} = \mu_{\text{grand}} + (z \cdot \sigma_{\text{grand}})$.
   - Results are persisted in `NormalizedScore` with `method='zscore'` and full diagnostic metadata.
6. **Data Export**: Organizers export datasets via `GET /api/export.csv` or the `export_judging_data` CLI command.

---

## 3. Key Technical Decisions & Justifications

### Decision 1: Per-Event Roles (`EventRole`) vs. Global User Roles
- **Context**: In multi-event platforms, a user may be a Participant submitting a project in Event 1, an assigned Judge in Event 2, and an Organizer managing Event 3.
- **Decision**: Platform-wide identity is decoupled from per-event permissions. The global `User` model links 1-to-1 with `accounts.Profile` solely for profile information. Authorization within any event is mediated through `events.EventRole` (and related `TeamMembership` and `JudgeAssignment` records). System administrators are managed via Django's `is_staff` / `is_superuser`.
- **Outcome**: Clean multi-tenancy across events without role collisions. Permission checks (`is_event_organizer`, `is_event_judge`) operate in $O(1)$ database query time with indexed compound lookups (`event`, `user`, `role`).

### Decision 2: Z-Score Score Normalization with Persisted Outputs
- **Context**: Different judges exhibit different leniency/harshness biases. A raw 4/5 from a harsh judge represents higher relative praise than a 4/5 from a lenient judge who assigns 5 to everyone.
- **Decision**: We standardize scores using per-judge z-score standardization ($z = \frac{x - \mu_j}{\sigma_j}$), mapping scores back to the rubric scale using the grand mean and pooled variance.
- **Persistence Strategy**: Rather than computing normalization on-the-fly during page requests, the output is explicitly computed via `run_score_normalization` and stored in `NormalizedScore` with `method='zscore'`.
- **Outcome**: Deterministic, reproducible rankings. Organizers can inspect before-and-after ranking shifts, review diagnostic variance statistics, and provide a tamper-evident audit trail for awards.

### Decision 3: Pure Algorithmic Judge Assignment with Conflict of Interest (COI) Exclusion
- **Context**: Manual judge assignment is prone to bias, workload imbalance, and accidental conflicts of interest.
- **Decision**: The assignment algorithm (`assign_judges`) is implemented as a pure, deterministic Python function decoupled from the Django ORM. It accepts raw integer IDs: `judges`, `submissions`, `k`, and an `exclusions` mapping (`submission_id -> set of excluded judge_ids`).
- **Workload Balancing**: The algorithm tracks judge assignment counts and uses a greedy min-workload selection with a deterministic hash tie-breaker (`(judge_id * 31 + sub_id * 17) % 10007`).
- **Outcome**: Guaranteed Conflict of Interest exclusion (no participant evaluates their own or their teammates' projects), balanced workload across judges (maximum delta between any two judges $\le 1$), and testability with synthetic test datasets without database overhead.

### Decision 4: Dynamic Custom Question Schema & Multi-Layer Validation
- **Context**: Hackathons require organizers to collect event-specific information (e.g., target architecture, specific APIs used, hardware requirements) without schema migrations for each new event.
- **Decision**: Organizers define typed questions using `CustomQuestion` (`text`, `textarea`, `url`, `select`, `checkbox`). `Submission.custom_answers` stores answers in a single PostgreSQL `JSONField`.
- **Validation Engine**: Server-side validation in `Submission.validate_custom_answers()` executes against the event's `CustomQuestion` records:
  - Orphaned / disallowed question IDs are rejected.
  - Allowed select choices are strictly validated against `question.choices`.
  - Type checking ensures valid boolean values for checkboxes and valid URL schemas for URLs.
  - Required fields are strictly validated when a submission transitions to `submitted`.
- **Outcome**: Dynamic flexibility for organizers combined with strict schema validation preventing malformed or invalid inputs.

### Decision 5: Two-Tier Deadline Enforcement & Immutable Version History
- **Context**: Hackathon submissions are subject to hard deadlines. Edits after the deadline must be rejected, and pre-deadline draft revisions must be auditable to resolve intellectual property or plagiarism disputes.
- **Decision**:
  - **Two-Tier Deadline**: Checked at both the view layer and the model `clean()` layer. Any edit attempted when `now() > event.submission_deadline` raises a `ValidationError` / HTTP 403 Forbidden and writes a `submission.deadline_blocked_edit_attempt` entry to `AuditLogEntry`.
  - **Immutable Version Snapshots**: In addition to `updated_at`, every successful save creates a sequential row in `SubmissionVersion` capturing `version_number`, title, description, custom answers, and author.
- **Outcome**: Absolute deadline integrity that cannot be bypassed via internal ORM updates or API calls, accompanied by a complete historical revision record.
