from kaoyan_agent.repositories.motivation import MotivationRepository


class FortuneRepository(MotivationRepository):
    """Formal name for fortune card persistence."""


__all__ = ["FortuneRepository", "MotivationRepository"]
