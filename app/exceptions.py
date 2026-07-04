class APIError(Exception):
    """Base class for all handled application errors.

    Carries an HTTP status code plus an (error, message) pair so the
    global exception handler in main.py can turn any of these into the
    consistent {"error": ..., "message": ...} response shape required
    by the assignment.
    """

    status_code = 500
    error_type = "InternalError"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(APIError):
    status_code = 404
    error_type = "NotFound"


class ValidationError(APIError):
    status_code = 422
    error_type = "ValidationError"


class ConflictError(APIError):
    status_code = 409
    error_type = "ConflictError"


class UnauthorizedError(APIError):
    status_code = 401
    error_type = "Unauthorized"


class BadRequestError(APIError):
    status_code = 400
    error_type = "BadRequest"
