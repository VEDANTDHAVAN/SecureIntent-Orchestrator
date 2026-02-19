class SecureIntentError(Exception):
    """Base exception for all SecureIntent errors."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthError(SecureIntentError):
    """Raised on authentication or authorisation failures."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class NotFoundError(SecureIntentError):
    """Raised when a requested resource does not exist."""
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} not found", status_code=404)


class DBError(SecureIntentError):
    """Raised on unexpected database errors."""
    def __init__(self, message: str = "Database error"):
        super().__init__(message, status_code=503)
