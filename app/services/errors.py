class BusinessError(Exception):
    def __init__(self, message: str, errors: dict[str, str] | None = None):
        super().__init__(message)
        self.errors = errors or {}


class NotFoundError(Exception):
    pass
