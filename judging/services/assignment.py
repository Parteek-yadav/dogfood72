"""
Pure algorithmic assignment engine and database service for Judge Assignments.

Guarantees:
1. Strict Conflict of Interest (COI) exclusion: no judge is assigned to a submission
   from a team they belong to or created.
2. Balanced workload: assignments are distributed as evenly as possible across all available judges.
3. Deterministic, testable pure function decoupled from Django ORM.
"""

from typing import List, Tuple, Dict, Set, Optional
from collections import defaultdict
import heapq

from django.db import transaction
from django.utils import timezone

from events.models import Event, EventRole
from teams.models import TeamMembership
from submissions.models import Submission
from judging.models import JudgeAssignment
from core.models import AuditLogEntry


def assign_judges(
    judges: List[int],
    submissions: List[int],
    k: int = 3,
    exclusions: Optional[Dict[int, Set[int]]] = None
) -> List[Tuple[int, int]]:
    """
    Pure algorithmic function assigning each submission to K judges.

    Parameters:
    -----------
    judges : List[int]
        List of judge user IDs.
    submissions : List[int]
        List of submission IDs.
    k : int
        Target number of distinct judges per submission (default 3).
    exclusions : Optional[Dict[int, Set[int]]]
        Mapping of submission_id -> set of excluded judge user IDs (e.g. COI / team members).

    Returns:
    --------
    List[Tuple[int, int]]
        List of (judge_id, submission_id) pairs.
    """
    if not judges or not submissions or k <= 0:
        return []

    exclusions = exclusions or {}
    judge_counts = {j_id: 0 for j_id in judges}
    assignments: List[Tuple[int, int]] = []

    # Sort submissions deterministically
    sorted_submissions = sorted(submissions)

    for sub_id in sorted_submissions:
        excluded_for_sub = exclusions.get(sub_id, set())
        # Filter eligible judges who do not have a conflict of interest
        eligible_judges = [j for j in judges if j not in excluded_for_sub]

        if not eligible_judges:
            continue

        target_k = min(k, len(eligible_judges))

        # Select target_k judges with the lowest current workload
        # Tie-breaker uses judge ID to maintain strict determinism
        sorted_candidates = sorted(
            eligible_judges,
            key=lambda j: (judge_counts[j], (j * 31 + sub_id * 17) % 10007, j)
        )

        selected_judges = sorted_candidates[:target_k]

        for judge_id in selected_judges:
            assignments.append((judge_id, sub_id))
            judge_counts[judge_id] += 1

    return assignments


@transaction.atomic
def run_event_judge_assignments(
    event: Event,
    k: int = 3,
    clear_existing: bool = True,
    actor=None
) -> List[JudgeAssignment]:
    """
    Executes algorithmic judge assignment for an Event in the database.
    Gathers all active judges, submitted projects, and COI exclusions,
    calls `assign_judges`, and persists `JudgeAssignment` records.
    """
    # 1. Fetch judges assigned to this event
    judge_user_ids = list(
        EventRole.objects.filter(event=event, role=EventRole.Role.JUDGE)
        .values_list('user_id', flat=True)
        .distinct()
    )

    # 2. Fetch all officially submitted projects
    submission_ids = list(
        Submission.objects.filter(event=event, status=Submission.Status.SUBMITTED)
        .values_list('id', flat=True)
        .distinct()
    )

    # 3. Build Conflict of Interest (COI) exclusions:
    # A judge who is a member or creator of a submission's team cannot judge that submission
    coi_map: Dict[int, Set[int]] = defaultdict(set)

    submissions = Submission.objects.filter(id__in=submission_ids).select_related('team')
    for sub in submissions:
        # Team creator
        coi_map[sub.id].add(sub.team.created_by_id)
        # All team members
        member_ids = TeamMembership.objects.filter(team=sub.team).values_list('user_id', flat=True)
        for m_id in member_ids:
            coi_map[sub.id].add(m_id)

    # 4. Run pure assignment algorithm
    assignment_pairs = assign_judges(
        judges=judge_user_ids,
        submissions=submission_ids,
        k=k,
        exclusions=coi_map
    )

    # 5. Persist assignments
    if clear_existing:
        # Only remove assignments that haven't been completed yet
        JudgeAssignment.objects.filter(event=event, status=JudgeAssignment.Status.ASSIGNED).delete()

    created_assignments: List[JudgeAssignment] = []
    for judge_id, sub_id in assignment_pairs:
        obj, created = JudgeAssignment.objects.get_or_create(
            event=event,
            judge_id=judge_id,
            submission_id=sub_id,
            defaults={'status': JudgeAssignment.Status.ASSIGNED}
        )
        created_assignments.append(obj)

    # 6. Audit log
    AuditLogEntry.log(
        action='judging.assignments_generated',
        target=event,
        actor=actor,
        metadata={
            'judge_count': len(judge_user_ids),
            'submission_count': len(submission_ids),
            'k': k,
            'total_assignments_created': len(created_assignments)
        }
    )

    return created_assignments
