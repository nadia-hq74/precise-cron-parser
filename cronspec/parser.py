"""Parsing for standard 5-field cron expressions (minute hour day month weekday),
plus the usual @daily/@hourly style shorthand.

The point of this module is not just "does this string parse" but "if it
doesn't, exactly where and why". Every error carries a line and column so
a caller can underline the offending character the way a compiler would.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet, List, Tuple

from .errors import CronSyntaxError

FIELD_NAMES = ("minute", "hour", "day of month", "month", "day of week")
FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

_MONTH_NAMES = {
    name: index + 1
    for index, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )
}
_WEEKDAY_NAMES = {
    name: index for index, name in enumerate(["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"])
}

# Standard cron shorthand. @reboot is deliberately left out: it isn't a time
# based schedule and doesn't fit CronSchedule.matches().
_MACROS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


@dataclass(frozen=True)
class CronSchedule:
    minute: FrozenSet[int]
    hour: FrozenSet[int]
    day: FrozenSet[int]
    month: FrozenSet[int]
    weekday: FrozenSet[int]
    expression: str

    def matches(self, moment: datetime) -> bool:
        """True if `moment` falls on this schedule.

        Day-of-month and day-of-week combine with cron's traditional OR
        rule: if both fields are restricted (neither is "*"), a match on
        either one is enough.
        """
        if moment.minute not in self.minute:
            return False
        if moment.hour not in self.hour:
            return False
        if moment.month not in self.month:
            return False

        dom_restricted = self.day != frozenset(range(1, 32))
        dow_restricted = self.weekday != frozenset(range(0, 8))
        dom_match = moment.day in self.day
        dow_match = (moment.isoweekday() % 7) in self.weekday

        if dom_restricted and dow_restricted:
            return dom_match or dow_match
        if dom_restricted:
            return dom_match
        if dow_restricted:
            return dow_match
        return True


def parse(expression: str) -> CronSchedule:
    """Parse a single cron expression. Errors are reported as line 1."""
    return _parse_line(expression, 1)


def parse_many(text: str) -> List[CronSchedule]:
    """Parse a document of one cron expression per line.

    Blank lines and lines starting with '#' are skipped. Every other line
    must be a complete 5-field expression; an error reports the real line
    number from `text`.
    """
    schedules = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        schedules.append(_parse_line(raw_line, line_no))
    return schedules


def _parse_macro(fields: List[Tuple[str, int]], text: str, line_no: int) -> CronSchedule:
    token, col_offset = fields[0]

    if len(fields) > 1:
        _, extra_col = fields[1]
        raise CronSyntaxError(
            f"macro {token!r} does not take additional fields, found {len(fields) - 1} extra",
            line_no,
            extra_col + 1,
            text,
        )

    expansion = _MACROS.get(token.lower())
    if expansion is None:
        raise CronSyntaxError(
            f"unknown macro {token!r} (expected one of {', '.join(sorted(_MACROS))})",
            line_no,
            col_offset + 1,
            text,
        )

    expanded = _parse_line(expansion, line_no)
    return CronSchedule(
        minute=expanded.minute,
        hour=expanded.hour,
        day=expanded.day,
        month=expanded.month,
        weekday=expanded.weekday,
        expression=text.strip(),
    )


def _split_fields(text: str) -> List[Tuple[str, int]]:
    fields = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i] in " \t":
            i += 1
        if i >= n:
            break
        start = i
        while i < n and text[i] not in " \t":
            i += 1
        fields.append((text[start:i], start))
    return fields


def _split_commas(raw: str) -> List[Tuple[str, int]]:
    segments = []
    start = 0
    for i, ch in enumerate(raw):
        if ch == ",":
            segments.append((raw[start:i], start))
            start = i + 1
    segments.append((raw[start:], start))
    return segments


def _parse_line(text: str, line_no: int) -> CronSchedule:
    fields = _split_fields(text)

    if fields and fields[0][0].startswith("@"):
        return _parse_macro(fields, text, line_no)

    if len(fields) < 5:
        last_end = fields[-1][1] + len(fields[-1][0]) if fields else 0
        raise CronSyntaxError(
            f"expected 5 fields (minute hour day month weekday), found {len(fields)}",
            line_no,
            last_end + 1,
            text,
        )
    if len(fields) > 5:
        extra_raw, extra_col = fields[5]
        raise CronSyntaxError(
            f"expected 5 fields (minute hour day month weekday), found {len(fields)}",
            line_no,
            extra_col + 1,
            text,
        )

    parsed = []
    for index, (raw, col_offset) in enumerate(fields):
        name = FIELD_NAMES[index]
        lo, hi = FIELD_RANGES[index]
        names_map = _MONTH_NAMES if index == 3 else (_WEEKDAY_NAMES if index == 4 else None)

        values = set()
        for segment, seg_offset in _split_commas(raw):
            abs_col = col_offset + seg_offset + 1
            values |= _parse_element(segment, abs_col, name, lo, hi, names_map, line_no, text)
        parsed.append(frozenset(values))

    return CronSchedule(
        minute=parsed[0],
        hour=parsed[1],
        day=parsed[2],
        month=parsed[3],
        weekday=parsed[4],
        expression=text.strip(),
    )


def _parse_element(elem, abs_col, name, lo, hi, names_map, line_no, source_line):
    if elem == "":
        raise CronSyntaxError(f"empty value in {name} field", line_no, abs_col, source_line)

    base, step = elem, None
    if "/" in elem:
        base, _, step_str = elem.partition("/")
        step_col = abs_col + len(base) + 1
        if base == "":
            raise CronSyntaxError(
                f"missing value before '/' in {name} field", line_no, abs_col, source_line
            )
        if step_str == "":
            raise CronSyntaxError(
                f"missing step value after '/' in {name} field", line_no, step_col, source_line
            )
        if not step_str.isdigit():
            raise CronSyntaxError(
                f"step value {step_str!r} is not a number in {name} field",
                line_no,
                step_col,
                source_line,
            )
        step = int(step_str)
        if step <= 0:
            raise CronSyntaxError(
                f"step value must be positive in {name} field", line_no, step_col, source_line
            )

    if base == "*":
        range_lo, range_hi = lo, hi
    elif "-" in base:
        lo_str, _, hi_str = base.partition("-")
        hi_col = abs_col + len(lo_str) + 1
        if lo_str == "":
            raise CronSyntaxError(
                f"missing range start before '-' in {name} field", line_no, abs_col, source_line
            )
        if hi_str == "":
            raise CronSyntaxError(
                f"missing range end after '-' in {name} field", line_no, hi_col, source_line
            )
        range_lo = _parse_value(lo_str, abs_col, name, lo, hi, names_map, line_no, source_line)
        range_hi = _parse_value(hi_str, hi_col, name, lo, hi, names_map, line_no, source_line)
        if range_hi < range_lo:
            raise CronSyntaxError(
                f"range end {hi_str!r} is smaller than start {lo_str!r} in {name} field",
                line_no,
                abs_col,
                source_line,
            )
    else:
        value = _parse_value(base, abs_col, name, lo, hi, names_map, line_no, source_line)
        range_lo = range_hi = value

    values = range(range_lo, range_hi + 1)
    if step is not None:
        values = values[::step]

    result = set()
    for v in values:
        if name == "day of week" and v == 7:
            v = 0  # 7 is a common alias for Sunday alongside 0
        result.add(v)
    return result


def _parse_value(token, col, name, lo, hi, names_map, line_no, source_line):
    if names_map is not None and token.upper() in names_map:
        return names_map[token.upper()]
    if not token.isdigit():
        hint = " (expected a number or a name)" if names_map else " (expected a number)"
        raise CronSyntaxError(
            f"{token!r} is not a valid value for {name} field{hint}", line_no, col, source_line
        )
    value = int(token)
    if not (lo <= value <= hi):
        raise CronSyntaxError(
            f"value {value} is out of range for {name} field (expected {lo}-{hi})",
            line_no,
            col,
            source_line,
        )
    return value
