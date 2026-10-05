import logging
from typing import Dict, List, Optional, Set, Type
from app.crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)

class CrawlerRegistry:
    """Dynamic registry for crawler adapters."""

    def __init__(self):
        self._classes: Dict[str, Type[BaseCrawler]] = {}
        self._instances: Dict[str, BaseCrawler] = {}

    def register(self, crawler_cls: Type[BaseCrawler], name: Optional[str] = None, services: Optional[Set[str]] = None):
        provider_name = (name or getattr(crawler_cls, "provider_name", "")).lower()
        if not provider_name:
            raise ValueError(f"Crawler class {crawler_cls.__name__} must define 'provider_name' or specify name.")

        if services:
            crawler_cls.supported_services = services
        crawler_cls.provider_name = provider_name

        self._classes[provider_name] = crawler_cls
        # Reset cached instance so next get instantiates fresh
        self._instances.pop(provider_name, None)
        logger.info(f"Registered crawler provider: {provider_name} for services {crawler_cls.supported_services}")

    def get_crawler(self, name: str) -> Optional[BaseCrawler]:
        name_lower = name.lower()
        if name_lower not in self._instances:
            cls = self._classes.get(name_lower)
            if not cls:
                return None
            self._instances[name_lower] = cls()
        return self._instances[name_lower]

    def get_crawlers_for_service(self, service: str, requested_providers: Optional[List[str]] = None) -> List[BaseCrawler]:
        crawlers = []
        filter_set = {p.lower() for p in requested_providers} if requested_providers else None

        for name in list(self._classes.keys()):
            if filter_set and name not in filter_set:
                continue
            crawler = self.get_crawler(name)
            if crawler and crawler.supports_service(service):
                crawlers.append(crawler)
        return crawlers

    def list_providers(self) -> List[dict]:
        providers = []
        for name, cls in self._classes.items():
            providers.append({
                "name": name,
                "services": sorted(list(cls.supported_services)),
            })
        return sorted(providers, key=lambda x: x["name"])

    def clear(self):
        self._classes.clear()
        self._instances.clear()

crawler_registry = CrawlerRegistry()

def register_crawler(name: Optional[str] = None, services: Optional[Set[str]] = None):
    """Decorator to register crawler adapters dynamically."""
    def decorator(cls: Type[BaseCrawler]):
        crawler_registry.register(cls, name=name, services=services)
        return cls
    return decorator
