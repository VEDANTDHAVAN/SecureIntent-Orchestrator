from enum import Enum

APP_NAME = "SecureIntent Orchestrator"
APP_VERSION = "0.1.0"

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 10080


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    APPROVER = "approver"
