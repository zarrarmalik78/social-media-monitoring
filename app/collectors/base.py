"""Abstract Base Collector interface and exception hierarchy."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.models.post import NormalizedPost


class CollectorError(Exception):
    """Base exception for all collector errors."""
    pass


class NoAccountError(CollectorError):
    """Raised when no active accounts are available in the collector account pool."""
    pass


class AuthError(CollectorError):
    """Raised when authentication or session cookies fail."""
    pass


class RateLimitError(CollectorError):
    """Raised when rate limits are exhausted and no standby accounts are available."""
    pass


class NetworkError(CollectorError):
    """Raised when connectivity or remote server errors occur."""
    pass


class BaseCollector(ABC):
    """Abstract interface defining standard collector behavior for any social network."""

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 20,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search the platform for posts matching the given query string.
        
        Args:
            query: The search keywords or advanced search query.
            limit: Maximum number of posts to retrieve.
            kwargs: Platform-specific options.
            
        Returns:
            List of NormalizedPost objects.
        """
        pass

    @abstractmethod
    async def check_status(self) -> Dict[str, Any]:
        """Check collector health, account pool readiness, and active sessions.
        
        Returns:
            Dictionary with status indicators and account pool details.
        """
        pass
