"""GPA 與等第換算工具（接在 StudentGrade 的總成績上）。

換算表集中在 GRADE_SCALE，如學校規定不同，只需修改此處即可。
格式：(最低分數, 等第, 績點)，由高到低排列。
"""
from decimal import Decimal, ROUND_HALF_UP

GRADE_SCALE = [
    (90, "A+", Decimal("4.3")),
    (85, "A",  Decimal("4.0")),
    (80, "A-", Decimal("3.7")),
    (77, "B+", Decimal("3.3")),
    (73, "B",  Decimal("3.0")),
    (70, "B-", Decimal("2.7")),
    (67, "C+", Decimal("2.3")),
    (63, "C",  Decimal("2.0")),
    (60, "C-", Decimal("1.7")),
    (50, "D",  Decimal("1.0")),
    (0,  "E",  Decimal("0.0")),
]


def score_to_letter_gp(score):
    """總成績 -> (等第, 績點)；尚無成績回傳 (None, None)。"""
    if score is None:
        return None, None
    for minimum, letter, gp in GRADE_SCALE:
        if score >= minimum:
            return letter, gp
    return "E", Decimal("0.0")


def calc_gpa(items):
    """items: 可迭代的 (總成績, 學分)。只納入已評定完成的課程，回傳 GPA 或 None。"""
    weighted = Decimal("0")
    credits = 0
    for score, credit in items:
        _, gp = score_to_letter_gp(score)
        if gp is None:
            continue
        weighted += gp * credit
        credits += credit
    if not credits:
        return None
    return (weighted / credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
