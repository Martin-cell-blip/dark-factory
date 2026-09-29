"""The error envelope of spec section 5: every 4xx and 5xx carries {"error": {code, message}}."""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def malformed(message: str) -> ApiError:
    return ApiError(400, "malformed_request", message)


def validation(message: str) -> ApiError:
    return ApiError(422, "validation_failed", message)


def unauthenticated(message: str = "missing, malformed or unknown bearer token") -> ApiError:
    return ApiError(401, "unauthenticated", message)


def forbidden(message: str) -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(message: str) -> ApiError:
    return ApiError(404, "not_found", message)


def insufficient_funds() -> ApiError:
    return ApiError(409, "insufficient_funds", "the balance is below the amount")


def request_not_pending(status: str) -> ApiError:
    return ApiError(409, "request_not_pending", f"the request is {status}")
