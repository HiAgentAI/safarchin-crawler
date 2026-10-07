"""Crawlers base, registry and adapters."""
from app.crawlers.base import BaseCrawler
from app.crawlers.registry import crawler_registry, register_crawler
from app.crawlers.alibaba.crawler import AlibabaCrawler
from app.crawlers.flytoday.crawler import FlyTodayCrawler
from app.crawlers.iranbus.crawler import IranBusCrawler
from app.crawlers.karnaval.crawler import KarnavalCrawler
from app.crawlers.jajiga.crawler import JajigaCrawler
from app.crawlers.safarchin.crawler import SafarchinCrawler
from app.crawlers.iranhotel.crawler import IranHotelCrawler
from app.crawlers.openstreetmap.crawler import OpenStreetMapCrawler

__all__ = [
    "BaseCrawler",
    "crawler_registry",
    "register_crawler",
    "AlibabaCrawler",
    "FlyTodayCrawler",
    "IranBusCrawler",
    "KarnavalCrawler",
    "JajigaCrawler",
    "SafarchinCrawler",
    "IranHotelCrawler",
    "OpenStreetMapCrawler",
]


