-- 1. Audit count by year
SELECT
    EXTRACT(YEAR FROM week_start)::int AS year,
    COUNT(*) AS audit_weeks,
    COUNT(*) FILTER (WHERE overall_grade = 'A') AS grade_a,
    COUNT(*) FILTER (WHERE overall_grade = 'B') AS grade_b,
    COUNT(*) FILTER (WHERE overall_grade = 'C') AS grade_c
FROM weekly_audit
GROUP BY EXTRACT(YEAR FROM week_start)::int
ORDER BY year;

-- 2. Item count by week
SELECT
    wa.week_start,
    wa.overall_grade,
    wa.green_count,
    wa.yellow_count,
    wa.red_count,
    COUNT(wai.id) AS item_count
FROM weekly_audit wa
LEFT JOIN weekly_audit_item wai
    ON wai.week_start = wa.week_start
GROUP BY
    wa.week_start,
    wa.overall_grade,
    wa.green_count,
    wa.yellow_count,
    wa.red_count
ORDER BY wa.week_start DESC
LIMIT 60;

-- 3. Weeks missing 8 audit items
SELECT
    wa.week_start,
    COUNT(wai.id) AS item_count
FROM weekly_audit wa
LEFT JOIN weekly_audit_item wai
    ON wai.week_start = wa.week_start
GROUP BY wa.week_start
HAVING COUNT(wai.id) <> 8
ORDER BY wa.week_start DESC;

-- 4. Recent audit detail
SELECT
    wa.week_start,
    wa.overall_grade,
    wai.sort_order,
    wai.item_label,
    wai.status,
    wai.summary,
    wai.evidence_json
FROM weekly_audit wa
JOIN weekly_audit_item wai
    ON wai.week_start = wa.week_start
ORDER BY wa.week_start DESC, wai.sort_order
LIMIT 80;
