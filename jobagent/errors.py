class JobAgentError(Exception):
    """Erreur de base."""


class ConfigError(JobAgentError):
    """Configuration invalide ou incomplète."""


class SourceError(JobAgentError):
    """Une source d'offres a répondu par une erreur ou une réponse inexploitable."""


class ScoreError(JobAgentError):
    """Le modèle n'a pas renvoyé un score exploitable."""
