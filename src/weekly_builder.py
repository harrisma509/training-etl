from datetime import date, datetime, timedelta


HARD_BANDS = {"Very Hard", "Epic Hard"}


def build_weekly_training(daily_rows):
    if not daily_rows:
        return []

    daily_by_date = {}

    for row in daily_rows:
        d = parse_date(row["date"])
        daily_by_date[d] = row

    min_date = min(daily_by_date.keys())
    max_date = max(daily_by_date.keys())

    week_starts = []
    current_week = week_start_monday(min_date)
    last_week = week_start_monday(max_date)

    while current_week <= last_week:
        week_starts.append(current_week)
        current_week += timedelta(days=7)

    weekly_rows = []
    prior_week_load = None

    for ws in week_starts:
        week_days = [ws + timedelta(days=i) for i in range(7)]
        rows = [daily_by_date.get(d) for d in week_days if d in daily_by_date]

        total_load = sum_int(rows, "total_load")
        main_ride_load = sum_int(rows, "main_ride_load")
        other_load = sum_int(rows, "other_load")

        ride_count = sum_int(rows, "ride_count")
        walk_count = sum_int(rows, "walk_count")
        hike_count = sum_int(rows, "hike_count")
        strength_count = sum_int(rows, "strength_count")
        mobility_count = sum_int(rows, "mobility_count")
        ski_count = sum_int(rows, "ski_count")
        run_count = sum_int(rows, "run_count")
        other_count = sum_int(rows, "other_count")

        activity_days = sum(1 for row in rows if int_or_zero(row.get("total_load")) > 0)
        very_hard_epic_days = count_very_hard_epic_days(rows)

        chronic_daily_c = calculate_chronic_daily_c(daily_by_date, ws)
        chronic_weekly_cw = round(chronic_daily_c * 7, 1) if chronic_daily_c is not None else None

        ac_ratio = None
        if chronic_weekly_cw and chronic_weekly_cw > 0:
            ac_ratio = round(total_load / chronic_weekly_cw, 2)

        ramp_pct = None
        if prior_week_load is not None and prior_week_load > 0:
            ramp_pct = round((total_load - prior_week_load) / prior_week_load, 3)

        status_level, status_text = weekly_status(
            total_load=total_load,
            ac_ratio=ac_ratio,
            ramp_pct=ramp_pct,
            very_hard_epic_days=very_hard_epic_days,
            chronic_daily_c=chronic_daily_c,
        )

        remaining_to_20pct_ramp = None
        if prior_week_load is not None and prior_week_load > 0:
            remaining_to_20pct_ramp = max(0, round((prior_week_load * 1.2) - total_load))

        weekly_rows.append({
            "week_start": ws.isoformat(),
            "week_end": (ws + timedelta(days=6)).isoformat(),

            "total_load": total_load,
            "main_ride_load": main_ride_load,
            "other_load": other_load,

            "activity_days": activity_days,
            "ride_count": ride_count,
            "walk_count": walk_count,
            "hike_count": hike_count,
            "strength_count": strength_count,
            "mobility_count": mobility_count,
            "ski_count": ski_count,
            "run_count": run_count,
            "other_count": other_count,

            "very_hard_epic_days": very_hard_epic_days,

            "chronic_daily_c": chronic_daily_c,
            "chronic_weekly_cw": chronic_weekly_cw,
            "ac_ratio": ac_ratio,
            "ramp_pct": ramp_pct,
            "ramp_pct_display": pct_display(ramp_pct),

            "remaining_to_20pct_ramp": remaining_to_20pct_ramp,
            "status_level": status_level,
            "status_text": status_text,
        })

        prior_week_load = total_load

    return weekly_rows


def parse_date(value):
    if isinstance(value, date):
        return value

    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def week_start_monday(d):
    return d - timedelta(days=d.weekday())


def sum_int(rows, field):
    return sum(int_or_zero(row.get(field)) for row in rows if row)


def int_or_zero(value):
    if value in (None, ""):
        return 0

    return int(round(float(value)))


def count_very_hard_epic_days(rows):
    count = 0

    for row in rows:
        if not row:
            continue

        band = row.get("main_ride_band") or ""

        if band in HARD_BANDS:
            count += 1

    return count


def calculate_chronic_daily_c(daily_by_date, week_start):
    lookback_start = week_start - timedelta(days=28)
    lookback_end = week_start - timedelta(days=1)

    days = []
    current = lookback_start

    while current <= lookback_end:
        row = daily_by_date.get(current)
        load = int_or_zero(row.get("total_load")) if row else 0
        days.append(load)
        current += timedelta(days=1)

    active_or_available_days = sum(1 for load in days if load > 0)

    if active_or_available_days < 4:
        return None

    return round(sum(days) / 28, 1)


def weekly_status(total_load, ac_ratio, ramp_pct, very_hard_epic_days, chronic_daily_c):
    reasons = []

    if chronic_daily_c is None:
        return "Early", "Early: not enough prior history for chronic load"

    if ramp_pct is not None:
        if ramp_pct > 0.20:
            reasons.append("Ramp >20%")
        elif ramp_pct >= 0.10:
            reasons.append("Ramp 10-20%")

    if ac_ratio is not None:
        if ac_ratio > 1.50:
            reasons.append("A/C >1.50")
        elif ac_ratio >= 1.30:
            reasons.append("A/C 1.30-1.50")

    if very_hard_epic_days >= 3:
        reasons.append("3+ Very Hard/Epic days")
    elif very_hard_epic_days >= 2:
        reasons.append("2 Very Hard/Epic days")

    if any(reason in reasons for reason in ["Ramp >20%", "A/C >1.50", "3+ Very Hard/Epic days"]):
        return "Spike", "Spike: " + "; ".join(reasons)

    if reasons:
        return "Caution", "Caution: " + "; ".join(reasons)

    if total_load == 0:
        return "Recovery", "Recovery: no training load"

    if ac_ratio is not None and 0.80 <= ac_ratio <= 1.30:
        return "Steady", "Steady: load is in target range"

    if ac_ratio is not None and ac_ratio < 0.80:
        return "Low", "Low: below normal load"

    return "Steady", "Steady"


def pct_display(value):
    if value is None:
        return ""

    return f"{value * 100:.1f}%"