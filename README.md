# Dogfood 2026 - Hackathon Submission & Judging Platform

A self-contained, offline-first hackathon submission and evaluation portal built for the **Dogfood 2026** 72-hour engineering sprint. Runs locally via Docker Compose with zero external cloud dependencies, per-event role isolation, cryptographically random single-use invite tokens, and statistical cross-judge score normalization.

---

## What It Does

The platform coordinates hackathon lifecycles across the five roles defined in the specification:
1. **Visitor (Unauthenticated)**: Browses published events, views project submissions in the public gallery, and accesses OpenAPI documentation.
2. **Participant**: Forms or joins teams using single-use invite tokens, drafts project submissions, answers organizer-defined custom questions, and submits before the deadline.
3. **Judge**: Evaluates assigned submissions against weighted rubric criteria (1–5 scale) within the judging window; isolated from viewing other judges' scores.
4. **Organizer**: Creates and manages events, defines tracks and custom questions, oversees the judging dashboard, runs balanced assignments with Conflict of Interest (COI) exclusion, triggers score normalization, and exports CSV datasets.
5. **Admin**: System-wide platform administrator (Django staff/superuser) with global access to all events and the administrative portal.

### Key Capabilities
- **Event & Team Management (T1)**: Organizers manage event timelines. Participants form teams restricted to a single team per event, inviting teammates via cryptographically random, single-use, expiring tokens (`secrets.token_urlsafe(32)` stored in the database).
- **Submissions & Dynamic Form Validation (T1)**: Project drafts support markdown writeups, tech tags, repository links, demo URLs, and gallery images. Organizers configure typed custom questions (text, textarea, URL, dropdown select, boolean checkbox) that are strictly validated before submission.
- **Strict Deadline Enforcement & Version Audit History (T1)**: Submissions are guarded by a two-layer deadline lock (model `clean()` and view layer). Edits attempted after `event.submission_deadline` are blocked with HTTP 403 and logged to `AuditLogEntry`. Every revision generates an immutable audit snapshot in `SubmissionVersion`.
- **Judging Engine & Balanced Assignments (T2)**: Organizers create weighted rubrics (summing to 100%). A pure algorithmic assignment function distributes $K$ distinct judges per submission while strictly enforcing Conflict of Interest (COI) exclusions (excluding judges from judging teams they created or belong to) and balancing judge workloads.
- **Strict Role Isolation API (T2)**: Dedicated REST endpoints enforce evaluation privacy. Judges can only access their own assignments and scores. Attempts to view another judge's evaluation (e.g. `/api/judge/scores?judge=other_judge`) return HTTP 403 Forbidden.
- **Z-Score Normalization Engine (T2)**: Standardizes raw scores per judge ($z = \frac{x - \mu_j}{\sigma_j}$) to counteract harshness or leniency biases, rescaling results back to the 1–5 scale based on grand statistics. Results are persisted in `NormalizedScore` with before/after audit tracking.
- **Data Exports (T2)**: Web endpoints and management commands (`export_judging_data`) export raw scores, normalized scores, judge assignments, and final rankings to CSV.

---

## Quickstart (One Command)

### Prerequisites
- Docker Engine 24+ and Docker Compose v2+
- Port `8000` available locally

### Start the Application
```bash
docker compose up --build
```
`docker-compose.yml` provides working environment defaults out of the box. No manual `.env` configuration is required.

On boot, PostgreSQL initializes, database migrations execute automatically, and `seed_fixtures` populates the initial specification environment (`evt_01`).

### Authentication Headers for Acceptance Checker
During container startup, `seed_fixtures` seeds fixed session rows in Django's session store and outputs the four authentication headers for the acceptance suite:
```
=======================================================
  ACCEPTANCE CHECKER AUTHENTICATION HEADERS (Cookie)   
=======================================================
Cookie: sessionid=session_organizer_key
Cookie: sessionid=session_judge_a_key
Cookie: sessionid=session_judge_b_key
Cookie: sessionid=session_participant_key
=======================================================
```
These cookies map directly to pre-authenticated users (`organizer`, `judge_a`, `judge_b`, `participant`) in the database.

---

## Official Acceptance Checker & Verified Tiers

The repository includes configuration for the official acceptance suite via `.dogfood.toml` and the runner `run.py`.

### Running the Checker
With the containers running (`docker compose up`), execute the checker from the host:
```bash
python run.py .dogfood.toml
```

The checker runs 7 automated HTTP verification requests without logging in, attaching the role headers from `.dogfood.toml`:
1. `GET /projects` (Public, 200, verifies fixture project title exists in body)
2. `POST /projects/new` (Participant header -> 403 Forbidden, verifies deadline enforcement on closed event)
3. `GET /api/judge/scores` (Judge A header -> 200 OK, returns Judge A's scores)
4. `GET /api/judge/scores` (Participant header -> 403 Forbidden)
5. `GET /api/judge/scores?judge=judge_a` (Judge B header -> 403 Forbidden, verifies role isolation)
6. `GET /api/export.csv` (Organizer header -> 200 OK with CSV body)
7. `GET /api/export.csv` (Participant header -> 403 Forbidden)

### Acceptance Report Status
Output is saved to `acceptance-report.txt`. The final line of the acceptance report reads:
```
SUMMARY: claimed T1 T2, verified T1 T2
```

### Claimed & Verified Status:
- **Tier 1 (T1)**: **CLAIMED & VERIFIED** (Verified by acceptance checker & 14 unit/integration tests).
- **Tier 2 (T2)**: **CLAIMED & VERIFIED** (Verified by acceptance checker & 10 unit/integration tests).
- **Tier 3 (T3)**: **NOT CLAIMED** (Deferred; community voting views and IP rate limiting are incomplete).

---

## Seeded Environment & Key Endpoints

A fresh boot seeds event `evt_01` ("Dogfood 2026 Invitational") containing 30 judges, 40 submitted projects across 3 tracks, weighted rubric criteria, balanced judge assignments, and simulated scores with deliberate edge cases.

### Seeded Credentials
All passwords are set to `password123` (Admin: `admin123`).

| Role | Username | Purpose / Checker Mapping |
| :--- | :--- | :--- |
| **Admin** | `admin` | Superuser / Platform administrator |
| **Organizer** | `organizer` | Checker organizer (`session_organizer_key`) |
| **Judge A** | `judge_a` | Checker judge A (`session_judge_a_key`) |
| **Judge B** | `judge_b` | Checker judge B (`session_judge_b_key`) |
| **Participant** | `participant` | Checker participant (`session_participant_key`) |
| **Additional Judges** | `judge_01` to `judge_28` | Real event evaluation judges |

### Primary URLs & API Routes

| Interface / Endpoint | Route | Role / Perms |
| :--- | :--- | :--- |
| **Projects List** | `GET /projects` | Public (200) |
| **New Project** | `POST /projects/new` | Participant (403 when event closed) |
| **Judge Scores API** | `GET /api/judge/scores` | Judge (200) / Participant (403) |
| **CSV Export API** | `GET /api/export.csv` | Organizer / Admin (200) |
| **Event Gallery** | `GET /submissions/events/evt_01/gallery/` | Public |
| **Judging Progress Dashboard** | `GET /judging/events/1/progress/` | Organizer |
| **OpenAPI 3.0 Documentation** | `GET /api/docs/` | Public |
| **Django Administration** | `GET /admin/` | Staff / Admin |

---

## Testing & Verification Commands

### Automated Test Suite
Run the 24 Django unit and integration tests inside the web container:
```bash
docker compose exec web python manage.py test
```
*Result: 24 tests passed (0 failures, 0 errors).*

### Score Normalization Tool
Run z-score normalization on event `evt_01` and view before/after rankings:
```bash
docker compose exec web python manage.py compute_normalization --event 1
```

---

## Technical Details & Known Gaps

1. **Scoring Deadline Boundary**: In the Prompt 1 Event schema (`start_date`, `end_date`, `submission_deadline`, `voting_start`, `voting_end`), there is no standalone `judging_deadline` column. Scoring closure is enforced against `voting_end` (representing the evaluation period conclusion) with fallback to `end_date`.
2. **Zero-Variance Judge Detection**: When a judge gives the identical rating to all assigned projects (e.g. `judge_01` rating everything 3), standard deviation $\sigma_j = 0$. The normalization algorithm sets $z = 0.0$ to prevent division-by-zero, centering the score at the grand mean. However, the system does not yet display an automated fraud/warning flag on the organizer dashboard.
3. **Duplicate Submission Handling**: When multiple submissions share identical titles/slugs (as with the seeded edge-case duplicate submission for "AutoDev Copilot"), both records are retained in the database with descriptive tagging so organizers can review rather than silently dropping data.
4. **Tier 3 Community Voting**: While database schemas for `Vote` and `Comment` exist, the public voting views, ballot shuffling, and IP-hash rate limiting are not completed or claimed.
