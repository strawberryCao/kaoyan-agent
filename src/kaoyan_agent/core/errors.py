class AppError(RuntimeError):
    """Base error for application-level failures."""


class ConfigError(AppError):
    """Raised when runtime configuration is missing or invalid."""


class LLMError(AppError):
    """Raised when an LLM request fails outside the provider client."""


class JSONParseError(AppError):
    """Raised when structured model output cannot be parsed."""


class RepositoryError(AppError):
    """Raised when a persistence operation fails."""


class WorkflowError(AppError):
    """Raised when an orchestrated workflow cannot complete."""


