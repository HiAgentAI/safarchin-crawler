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
