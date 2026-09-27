"""
Score normalization service using per-judge z-score standardization.

Standardizes for judge leniency, harshness, and rating variance.
Stores outputs in `NormalizedScore` with method='zscore' for reproducible auditability.
"""

from decimal import Decimal
import math
from typing import Dict, List, Any, Optional
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from events.models import Event
from submissions.models import Submission
from judging.models import JudgeAssignment, Score, Rubric, RubricCriterion, NormalizedScore
from core.models import AuditLogEntry


def compute_weighted_submission_score(assignment: JudgeAssignment, rubric: Optional[Rubric] = None) -> Optional[float]:
    """
    Computes a judge's single overall score (1.0 - 5.0) for an assignment by
    applying criterion weights. Returns None if no scores exist.
    """
    scores = list(assignment.scores.select_related('criterion').all())
    if not scores:
        return None

    # Calculate weighted average
    total_weighted_points = Decimal('0.00')
    total_weight = Decimal('0.00')

    for sc in scores:
        w = sc.criterion.weight
        total_weighted_points += Decimal(sc.value) * w
        total_weight += w

    if total_weight <= 0:
        # Fallback to simple unweighted average
        return sum(sc.value for sc in scores) / len(scores)

    return float(total_weighted_points / total_weight)


@transaction.atomic
def run_score_normalization(event: Event, actor=None) -> Dict[str, Any]:
    """
    Executes z-score standardization across all judges for an Event.

    Steps:
    1. Compute weighted raw score for every (judge, submission) assignment.
    2. For each judge, compute their mean (mu_j) and stddev (sigma_j).
    3. Calculate individual z-scores: z = (score - mu_j) / sigma_j.
    4. Rescale z-scores to rubric 1–5 scale using grand mean and pooled variance.
    5. Aggregate submission normalized scores and persist into NormalizedScore.
    6. Return detailed before/after comparison diagnostics.
    """
    # 1. Fetch completed or scored assignments
    assignments = (
        JudgeAssignment.objects.filter(event=event)
        .select_related('judge', 'submission', 'event')
        .prefetch_related('scores__criterion')
    )

    # judge_id -> list of (submission_id, raw_score)
    judge_raw_evals: Dict[int, List[tuple]] = defaultdict(list)
    # submission_id -> list of raw_score
    sub_raw_scores: Dict[int, List[float]] = defaultdict(list)
    # assignment_key (judge_id, submission_id) -> raw_score
    assignment_scores: Dict[tuple, float] = {}

    all_raw_scores: List[float] = []

    for assign in assignments:
        val = compute_weighted_submission_score(assign)
        if val is not None:
            judge_raw_evals[assign.judge_id].append((assign.submission_id, val))
            sub_raw_scores[assign.submission_id].append(val)
            assignment_scores[(assign.judge_id, assign.submission_id)] = val
            all_raw_scores.append(val)

    if not all_raw_scores:
        return {
            'status': 'no_scores',
            'message': 'No evaluation scores found for this event.',
            'rankings': [],
        }

    # Grand statistics across all evaluations
    grand_mean = sum(all_raw_scores) / len(all_raw_scores)
    grand_variance = (
        sum((x - grand_mean) ** 2 for x in all_raw_scores) / (len(all_raw_scores) - 1)
        if len(all_raw_scores) > 1 else 1.0
    )
    grand_std = math.sqrt(grand_variance) if grand_variance > 0 else 1.0

    # 2. Per-judge statistics
    judge_stats = {}
    for j_id, evals in judge_raw_evals.items():
        scores_list = [s[1] for s in evals]
        count = len(scores_list)
        j_mean = sum(scores_list) / count
        if count > 1:
            j_var = sum((x - j_mean) ** 2 for x in scores_list) / (count - 1)
            j_std = math.sqrt(j_var) if j_var > 0 else 0.0
        else:
            j_std = 0.0

        judge_stats[j_id] = {
            'mean': j_mean,
            'std': j_std,
            'count': count,
        }

    # 3. Compute z-scores and rescaled normalized scores
    # submission_id -> list of rescaled normalized scores
    sub_normalized_scores: Dict[int, List[float]] = defaultdict(list)
    sub_z_scores: Dict[int, List[float]] = defaultdict(list)

    for (j_id, s_id), raw_val in assignment_scores.items():
        j_stat = judge_stats[j_id]
        j_mean = j_stat['mean']
        j_std = j_stat['std']

        # If judge standard deviation is 0 (all scores identical) or single rating,
        # z-score is 0 (aligns with judge average)
        if j_std > 0.0001:
            z = (raw_val - j_mean) / j_std
        else:
            z = 0.0

        # Rescale z back to 1.0 - 5.0 range centered at grand_mean
        rescaled = grand_mean + (z * grand_std)
        # Clamp to bounds [1.0, 5.0]
        rescaled_clamped = max(1.0, min(5.0, rescaled))

        sub_z_scores[s_id].append(z)
        sub_normalized_scores[s_id].append(rescaled_clamped)

    # 4. Save to NormalizedScore and build rankings comparison
    all_submissions = {
        s.id: s for s in Submission.objects.filter(event=event, id__in=sub_raw_scores.keys())
    }

    comparison_records = []

    for s_id, r_scores in sub_raw_scores.items():
        sub = all_submissions.get(s_id)
        if not sub:
            continue

        raw_mean = sum(r_scores) / len(r_scores)
        norm_scores = sub_normalized_scores[s_id]
        final_norm = sum(norm_scores) / len(norm_scores)
        z_list = sub_z_scores[s_id]

        # Persist model
        NormalizedScore.objects.update_or_create(
            submission=sub,
            method='zscore',
            defaults={
                'raw_mean': Decimal(str(round(raw_mean, 3))),
                'normalized_value': Decimal(str(round(final_norm, 3))),
                'metadata': {
                    'judge_count': len(r_scores),
                    'raw_scores': [round(x, 2) for x in r_scores],
                    'z_scores': [round(x, 3) for x in z_list],
                    'rescaled_scores': [round(x, 3) for x in norm_scores],
                    'grand_mean': round(grand_mean, 3),
                    'grand_std': round(grand_std, 3),
                }
            }
        )

        comparison_records.append({
            'submission_id': sub.id,
            'title': sub.title,
            'team_name': sub.team.name,
            'raw_mean': raw_mean,
            'normalized_score': final_norm,
            'eval_count': len(r_scores)
        })

    # Sort to determine raw ranks and normalized ranks
    # 1. Raw ranking
    comparison_records.sort(key=lambda x: -x['raw_mean'])
    for idx, rec in enumerate(comparison_records, start=1):
        rec['raw_rank'] = idx

    # 2. Normalized ranking
    comparison_records.sort(key=lambda x: -x['normalized_score'])
    for idx, rec in enumerate(comparison_records, start=1):
        rec['norm_rank'] = idx
        rec['rank_delta'] = rec['raw_rank'] - rec['norm_rank']

    # Compute judge variance comparison
    judge_means = [s['mean'] for s in judge_stats.values()]
    judge_raw_std = (
        math.sqrt(sum((m - grand_mean) ** 2 for m in judge_means) / len(judge_means))
        if judge_means else 0.0
    )

    result = {
        'status': 'success',
        'event_id': event.id,
        'event_name': event.name,
        'submission_count': len(comparison_records),
        'judge_count': len(judge_stats),
        'total_scores_evaluated': len(all_raw_scores),
        'grand_mean': round(grand_mean, 3),
        'grand_std': round(grand_std, 3),
        'judge_raw_std': round(judge_raw_std, 3),
        'rankings': comparison_records,
    }

    # Audit log
    AuditLogEntry.log(
        action='judging.normalization_computed',
        target=event,
        actor=actor,
        metadata={
            'method': 'zscore',
            'submissions_normalized': len(comparison_records),
            'grand_mean': round(grand_mean, 3),
            'judge_count': len(judge_stats)
        }
    )

    return result
