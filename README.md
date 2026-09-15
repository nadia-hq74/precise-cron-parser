# cronspec

A small Python library for parsing standard 5-field cron expressions
(`minute hour day month weekday`). No dependencies, no CLI, just a parser
you import.

## Why

Every cron library I've used tells you *that* an expression is invalid,
not *where*. You get `ValueError: invalid cron string` for a field buried
in the middle of a line you pasted from some ops runbook, and you're back
to counting characters by hand. cronspec tracks the exact line and column
of the problem and prints it the way a compiler would.

```pycon
>>> from cronspec import parse
>>> parse("*/abc 9 * * *")
Traceback (most recent call last):
  ...
cronspec.errors.CronSyntaxError: line 1, column 3: step value 'abc' is not a number in minute field
    */abc 9 * * *
      ^
```

```pycon
>>> parse("0 25 * * *")
Traceback (most recent call last):
  ...
cronspec.errors.CronSyntaxError: line 1, column 3: value 25 is out of range for hour field (expected 0-23)
    0 25 * * *
      ^
```

`parse_many` does the same thing across a whole file of expressions (one
per line, `#` comments and blank lines allowed) and reports the real line
number:

```pycon
>>> from cronspec import parse_many
>>> text = """
... # nightly jobs
... 0 2 * * *
... 0 3 * * 8
... """
>>> parse_many(text)
Traceback (most recent call last):
  ...
cronspec.errors.CronSyntaxError: line 4, column 9: value 8 is out of range for day of week field (expected 0-7)
    0 3 * * 8
            ^
```

## Usage

```python
from datetime import datetime
from cronspec import parse

schedule = parse("*/15 9-17 * * MON-FRI")

schedule.matches(datetime(2026, 9, 16, 9, 15))   # Wednesday, 9:15am -> True
schedule.matches(datetime(2026, 9, 19, 9, 15))   # Saturday -> False
schedule.matches(datetime(2026, 9, 16, 9, 20))   # not a multiple of 15 -> False
```

`parse` returns a `CronSchedule`, a frozen dataclass holding the resolved
set of valid values for each field (`minute`, `hour`, `day`, `month`,
`weekday`), plus a `matches(datetime)` method.

## Supported syntax

- `*` — every value
- single values: `5`, `MON`, `JAN`
- lists: `1,15,30`
- ranges: `9-17`, `MON-FRI`
- steps: `*/15`, `10-30/5`
- month names `JAN`-`DEC` and weekday names `SUN`-`SAT` (case-insensitive)
- `7` as an alias for Sunday in the weekday field, alongside `0`
- day-of-month/day-of-week combine with cron's traditional OR rule: if
  both fields are restricted, a match on either is enough

Not yet supported: `@daily`/`@hourly` style macros, a seconds field, and
`?`/`L`/`W` (Quartz-style) extensions.

## Status

Early. The parser and error reporting are solid; there's no scheduling
logic beyond `matches()` yet (no "next run time" helper). See the
package's issue tracker for what's planned next.

## License

MIT, see [LICENSE](LICENSE).
