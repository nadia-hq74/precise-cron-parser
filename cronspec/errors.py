"""Exception type used for every parse failure in this package."""


class CronSyntaxError(ValueError):
    """Raised when a cron expression cannot be parsed.

    Carries the 1-indexed line and column of the offending character so
    that callers (and this exception's own __str__) can point at exactly
    where things went wrong, the way a compiler would.
    """

    def __init__(self, message: str, line: int, column: int, source_line: str) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line
        super().__init__(self._format())

    def _format(self) -> str:
        pointer = " " * (self.column - 1) + "^"
        return (
            f"line {self.line}, column {self.column}: {self.message}\n"
            f"    {self.source_line}\n"
            f"    {pointer}"
        )

    def __str__(self) -> str:
        return self._format()
