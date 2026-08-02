class AppHTTPException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        code: str = "APP_ERROR",
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.code = code
        self.errors = errors
        super().__init__(message)
