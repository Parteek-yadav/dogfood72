# Dogfood 2026 - Threat Model & Security Posture

This document outlines the security architecture, threat model, defenses, and intentional boundaries for the Dogfood 2026 hackathon portal.

Grounded strictly in what is implemented in the codebase, this document follows the principle of honest disclosure: detailing what is fully prevented, what is partially mitigated, and what is explicitly not defended against.

---

## 1. Threat Surface Overview

The platform coordinates participants, evaluators, and administrators. The primary attack vectors are:
1. **Deadline Gaming**: Attempting to alter or submit code/materials after the hackathon submission deadline has closed.
2. **Judge Collusion & Evaluation Snooping**: Judges attempting to view peer evaluations to align scores, influence outcomes, or coordinate bias.
3. **Conflict of Interest (COI) Manipulation**: Evaluators scoring their own projects or projects created by their teammates.
4. **Zero-Variance / Careless Scoring**: Evaluators assigning uniform ratings to all projects to minimize effort or skew normalization.
5. **Sybil Voting & Ballot Stuffing**: Creating automated accounts or forging voter tokens to artificially inflate project popularity.
6. **Data Scraping & Draft Exfiltration**: Unauthorized access to private drafts, confidential organizer questions, or unreleased event outcomes.

---

## 2. Threat Analysis & Defensive Matrix

| Threat Vector | Status | Architectural Defense | Code Reference |
| :--- | :--- | :--- | :--- |
| **Post-Deadline Edits** | **Fully Prevented** | Two-tier enforcement: Model `clean()` and view-layer checks reject edits with HTTP 403 when `now() > event.submission_deadline`. | `submissions/models.py:105`, `submissions/views.py:79` |
| **Peer Score Snooping** | **Fully Prevented** | Strict role isolation in DRF views: queries for another judge's score return HTTP 403 Forbidden. | `judging/api.py:63, 168` |
| **Conflict of Interest (COI)** | **Fully Prevented** | Algorithmic assignment excludes team creators and team members from evaluating their own projects. | `judging/services/assignment.py:112` |
| **Multi-Team Collusion** | **Fully Prevented** | `TeamMembership` constraints and application logic strictly prevent a user from joining multiple teams in the same event. | `core/tests.py:183`, `teams/views.py:53` |
| **Evaluation Leniency Bias** | **Mitigated** | Cross-judge z-score standardization adjusts raw scores based on evaluator mean and variance. | `judging/services/normalization.py:48` |
| **Zero-Variance Scoring** | **Partially Mitigated** | Algorithm sets $z = 0.0$ to avoid division-by-zero, mapping score to grand mean. No automated alert banner currently exists. | `judging/services/normalization.py:129` |
| **Anonymous Ballot Stuffing** | **Partially Mitigated** | Dual constraints on `Vote` table enforce 1 vote per signed token or authenticated user ID, plus SHA256 IP hashing. | `voting/models.py:75` |
| **External Bot Farms / Distributed Sybils** | **Not Defended** | Distributed residential IP proxies rotating cookies can submit multiple anonymous votes if open-link voting is enabled. | Explicit known limitation |

---

## 3. Deep-Dive: Specific Threat Defenses

### 3.1 Deadline Gaming
- **What We Stop**: Any attempt to modify a submission's title, writeup, URLs, or custom question answers after `event.submission_deadline` has passed.
- **How It Works**:
  - View layer: The edit view immediately aborts with HTTP 403.
  - Model layer: Even if a view check were bypassed (e.g. via direct script or ORM update), `Submission.clean()` intercepts the save, raises a `ValidationError`, and logs `submission.deadline_blocked_edit_attempt` to `AuditLogEntry`.
  - Immutable snapshots: Every revision prior to the deadline creates a distinct `SubmissionVersion` row, providing a complete historical trail.
- **Limitations**: We do not defend against external repository updates if a team pushes new commits to an external GitHub repository after the deadline.

### 3.2 Judge Collusion & Peer Score Snooping
- **What We Stop**: A judge attempting to monitor other judges' evaluations before or during scoring.
- **How It Works**:
  - `GET /api/submissions/<id>/scores/` checks `is_event_organizer(submission.event, request.user)`. If the requester is not an organizer or admin, it raises `PermissionDenied` (HTTP 403).
  - `GET /api/judge/scores?judge=<other_judge>` checks `target_judge == request.user.username`. If a judge requests another evaluator's username, the request returns HTTP 403.
  - Endpoints do not return empty 200 lists (which could leak assignment existence); they strictly return 403.

### 3.3 Conflict of Interest (COI) in Assignments
- **What We Stop**: Judges being assigned to evaluate projects submitted by themselves or their teammates.
- **How It Works**:
  - `run_event_judge_assignments` iterates over all submitted projects and aggregates the team creator and all `TeamMembership` user IDs into an exclusion set for that project:
    ```python
    coi_map[sub.id].add(sub.team.created_by_id)
    for m_id in member_ids:
        coi_map[sub.id].add(m_id)
    ```
  - The pure assignment function `assign_judges` filters out any candidate judge whose ID is in `coi_map[sub.id]`.
- **Limitations**: We do not automatically detect off-platform social relationships or institutional affiliations that are not represented in the platform's team membership records.

### 3.4 Zero-Variance / Uniform Scoring
- **What We Do**: If an evaluator assigns the identical rating (e.g. all 3s) to all assigned submissions, sample variance is zero ($\sigma_j = 0$).
- **Mathematical Handling**: The normalization engine explicitly checks `if j_std > 0.0001` before dividing. If $\sigma_j \le 0.0001$, it assigns $z = 0.0$, which centers the normalized rating at the grand mean ($\mu_{\text{grand}}$). This prevents `ZeroDivisionError` crashes and prevents the lazy judge from artificially skewing project rankings.
- **What We Do NOT Do (Honest Gap)**: The platform does not currently flag this judge on the organizer dashboard or emit an automated fraud warning. The zero-variance evaluation is handled mathematically, but organizer notification is a manual inspection process via the progress dashboard or CSV export.

### 3.5 Sybil Voting & Ballot Stuffing
- **What We Stop**: A single authenticated user or browser repeatedly voting for the same project.
- **How It Works**:
  - Authenticated votes enforce a database-level partial unique constraint on `(submission, user) WHERE user IS NOT NULL`.
  - Anonymous votes enforce a partial unique constraint on `(submission, voter_token) WHERE voter_token IS NOT NULL`.
- **What We Do NOT Defend Against**:
  - If an organizer enables open-link anonymous voting, an attacker utilizing headless browsers and rotating IP proxies will generate new signed tokens and bypass IP hashing. True Sybil resistance for open-link voting requires external proof-of-humanity or SMS verification, which contradicts the offline-first zero-external-dependency requirement.

---

## 4. Audit Logging & Non-Repudiation

All critical security and administrative actions are logged to `AuditLogEntry`:
- `submission.created`, `submission.edited`, `submission.submitted`
- `submission.deadline_blocked_edit_attempt` (includes actor, attempted timestamp, deadline)
- `team.joined`, `team.invite_created`, `team.invite_used`
- `judging.assignments_generated`
- `score.submitted`
- `judging.normalization_computed`

These logs are stored in a append-only database table accessible to organizers and administrators.
