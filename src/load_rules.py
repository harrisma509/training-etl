from activity_utils import is_ski
from constants import (
    EASY_MULT,
    ENDUR_MULT,
    HARD_MULT,
    SKI_LOAD_BASE,
    SKI_LOAD_MAX,
    SKI_LOAD_MIN,
    SKI_RPE_STEP,
    SUPP_MIN_MOBI,
    SUPP_MIN_MULT,
    SUPP_MIN_WALK,
    VERYHARD_MULT,
)


def supplemental_load_for_other(row, rpe):
    minutes = row["moving_sec"] / 60.0
    sport = (row.get("sport_type") or "").lower().replace(" ", "")
    name = (row.get("name") or "").lower()

    if is_ski(row):
        return ski_load_from_rpe(rpe)

    if sport == "walk":
        return SUPP_MIN_WALK * minutes

    if sport == "yoga":
        return SUPP_MIN_MOBI * minutes

    if "mobility" in name or "stretch" in name:
        return SUPP_MIN_MOBI * minutes

    return SUPP_MIN_MULT * minutes


def ski_load_from_rpe(rpe):
    if rpe < 0:
        load = SKI_LOAD_BASE
    else:
        load = SKI_LOAD_BASE + SKI_RPE_STEP * (rpe - 5)

    return max(SKI_LOAD_MIN, min(SKI_LOAD_MAX, load))


def intensity_score_from_zones(z1, z2, z3, z4, z5):
    return (
        (z1 / 60.0) * 1.0
        + (z2 / 60.0) * 2.0
        + (z3 / 60.0) * 4.0
        + (z4 / 60.0) * 7.0
        + (z5 / 60.0) * 10.0
    )


def intensity_band(score, chronic_c):
    easy_max = round(EASY_MULT * chronic_c)
    endur_max = round(ENDUR_MULT * chronic_c)
    hard_max = round(HARD_MULT * chronic_c)
    very_hard_max = round(VERYHARD_MULT * chronic_c)

    if score <= easy_max:
        return "Easy"

    if score <= endur_max:
        return "Endurance"

    if score <= hard_max:
        return "Hard"

    if score <= very_hard_max:
        return "Very Hard"

    return "Epic Hard"


def round_half_up(value):
    return int(value + 0.5)