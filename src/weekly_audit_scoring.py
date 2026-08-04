"""
Weekly Audit overall scoring.

This module converts individual audit item statuses into the persisted
weekly_audit header row.

It owns:
- green/yellow/red item counts
- weighted G/Y/R overall scoring
- critical red risk checks
- compact audit summary text
- next-week action text

Individual audit item scoring belongs in weekly_audit_rules.py.
Database upsert logic belongs in weekly_audit_queries.py.
"""

from weekly_audit_config import (
    STATUS_GREEN,
    STATUS_YELLOW,
    STATUS_RED,
    GRADE_WEIGHTS,
    GATE_ITEM_KEYS,
    CRITICAL_ITEM_KEYS,
    STATUS_MULTIPLIERS,
)


def build_weekly_audit(week_start, items, computed_at):
    green_count = sum(1 for item in items if item["status"] == STATUS_GREEN)
    yellow_count = sum(1 for item in items if item["status"] == STATUS_YELLOW)
    red_count = sum(1 for item in items if item["status"] == STATUS_RED)

    weighted_score, critical_red_count, gate_flags = calculate_weighted_score(items)
    overall_grade = calculate_overall_grade(weighted_score, critical_red_count)
    audit_summary = build_audit_summary(items)
    next_week_action = build_next_week_action(overall_grade)

    return {
        "week_start": week_start,
        "audit_version": "v1",
        "overall_grade": overall_grade,
        "green_count": green_count,
        "yellow_count": yellow_count,
        "red_count": red_count,
        "audit_summary": audit_summary,
        "next_week_action": next_week_action,
        "source": "computed",
        "computed_at": computed_at,
    }


def calculate_weighted_score(items):
    weighted_score = 0.0
    critical_red_count = 0
    gate_flags = []

    for item in items:
        item_key = item["item_key"]
        status = item["status"]

        if item_key in GATE_ITEM_KEYS:
            if status == STATUS_RED:
                gate_flags.append(item_key)
            continue

        weight = GRADE_WEIGHTS.get(item_key)
        if weight is None:
            continue

        multiplier = STATUS_MULTIPLIERS.get(status, 0.0)
        weighted_score += weight * multiplier

        if item_key in CRITICAL_ITEM_KEYS and status == STATUS_RED:
            critical_red_count += 1

    return round(weighted_score, 1), critical_red_count, gate_flags


def calculate_overall_grade(weighted_score, critical_red_count):
    if critical_red_count >= 2:
        return "R"
    if weighted_score >= 80:
        return "G"
    if weighted_score >= 65:
        return "Y"
    return "R"


def build_audit_summary(items):
    problems = [item["summary"] for item in items if item["status"] != STATUS_GREEN]
    if not problems:
        return "All eight audit items look balanced"

    summary = ", ".join(problems[:3])
    if len(summary.split()) > 12:
        summary = "; ".join(problems[:2])
    return summary[:180]


def build_next_week_action(overall_grade):
    if overall_grade == "G":
        return "Build normally and maintain recovery balance"
    if overall_grade == "Y":
        return "Watch warning areas before adding intensity"
    return "Reduce load and prioritize recovery"
