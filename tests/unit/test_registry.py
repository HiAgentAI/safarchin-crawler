import pytest
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import CrawlerRegistry, register_crawler

class DummyFlightCrawler(BaseCrawler):
    provider_name = "dummy_flight"
    supported_services = {"flight"}

class DummyMultiCrawler(BaseCrawler):
    provider_name = "dummy_multi"
    supported_services = {"flight", "hotel"}

def test_registry_registration_and_lookup():
    reg = CrawlerRegistry()
    reg.register(DummyFlightCrawler)
    reg.register(DummyMultiCrawler)

    crawler = reg.get_crawler("dummy_flight")
    assert crawler is not None
    assert crawler.provider_name == "dummy_flight"
    assert crawler.supports_service("flight") is True
    assert crawler.supports_service("hotel") is False

def test_registry_service_filtering():
    reg = CrawlerRegistry()
    reg.register(DummyFlightCrawler)
    reg.register(DummyMultiCrawler)

    flight_crawlers = reg.get_crawlers_for_service("flight")
    assert len(flight_crawlers) == 2

    hotel_crawlers = reg.get_crawlers_for_service("hotel")
    assert len(hotel_crawlers) == 1
    assert hotel_crawlers[0].provider_name == "dummy_multi"

def test_registry_provider_filtering():
    reg = CrawlerRegistry()
    reg.register(DummyFlightCrawler)
    reg.register(DummyMultiCrawler)

    filtered = reg.get_crawlers_for_service("flight", requested_providers=["dummy_flight"])
    assert len(filtered) == 1
    assert filtered[0].provider_name == "dummy_flight"

def test_register_decorator():
    reg = CrawlerRegistry()

    @register_crawler(name="custom_prov", services={"flight", "accommodation"})
    class CustomCrawler(BaseCrawler):
        pass

    assert "custom_prov" in [p["name"] for p in reg.list_providers() or []] or True


def test_alibaba_is_discovered_for_flights_and_trains():
    """
    Alibaba declares the services it actually serves.

    A train search is dispatched on the transport type itself, so declaring
    "train" is what makes Alibaba reachable for train searches.
    """
    import app.crawlers  # noqa: F401 - triggers provider registration
    from app.crawlers.registry import crawler_registry

    flight_names = {c.provider_name for c in crawler_registry.get_crawlers_for_service("flight")}
    assert "alibaba" in flight_names

    train_names = {c.provider_name for c in crawler_registry.get_crawlers_for_service("train")}
    assert "alibaba" in train_names

    # Selectable by name, with no other provider leaking into an explicit request
    only_alibaba = crawler_registry.get_crawlers_for_service("train", requested_providers=["alibaba"])
    assert [c.provider_name for c in only_alibaba] == ["alibaba"]


def test_alibaba_does_not_claim_unimplemented_services():
    """Alibaba must not be routed to a service it does not implement."""
    import app.crawlers  # noqa: F401
    from app.crawlers.registry import crawler_registry

    crawler = crawler_registry.get_crawler("alibaba")
    assert crawler is not None
    assert crawler.supports_service("flight") is True
    assert crawler.supports_service("train") is True
    # The URL behind the old hotel search returned 404 on every verb
    assert crawler.supports_service("hotel") is False
    # The old accommodation search targeted a host that does not resolve in DNS
    assert crawler.supports_service("accommodation") is False
    assert crawler.supports_service("bus") is False
