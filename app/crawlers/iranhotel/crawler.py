import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.crawlers.base import BaseCrawler
from app.crawlers.registry import register_crawler
from app.schemas.hotel import (
    HotelSearchQuery,
    HotelResult,
    RoomOffer,
)
from app.schemas.accommodation import (
    AccommodationSearchQuery,
    AccommodationResult,
    ProvinceItem,
    CityItem,
)
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.http_client import ResilientHttpClient
from app.utils.calendar import to_jalali

logger = logging.getLogger(__name__)

# Common Iranian travel destinations mapped to IranHotelOnline URL slugs
CITY_SLUG_MAP: Dict[str, str] = {
    "tehran": "tehran",
    "تهران": "tehran",
    "mashhad": "mashhad",
    "مشهد": "mashhad",
    "shiraz": "shiraz",
    "شیراز": "shiraz",
    "isfahan": "isfahan",
    "esfahan": "isfahan",
    "اصفهان": "isfahan",
    "kish": "kish",
    "کیش": "kish",
    "yazd": "yazd",
    "یزد": "yazd",
    "tabriz": "tabriz",
    "تبریز": "tabriz",
    "qom": "qom",
    "قم": "qom",
    "ramsar": "ramsar",
    "رامسر": "ramsar",
    "rasht": "rasht",
    "رشت": "rasht",
    "gorgan": "gorgan",
    "گرگان": "gorgan",
    "bandarabbas": "bandarabbas",
    "بندرعباس": "bandarabbas",
    "qeshm": "qeshm",
    "قشم": "qeshm",
    "kerman": "kerman",
    "کرمان": "kerman",
    "kashan": "kashan",
    "کاشان": "kashan",
    "hamadan": "hamadan",
    "همدان": "hamadan",
    "sari": "sari",
    "ساری": "sari",
    "anzali": "anzali",
    "انزلی": "anzali",
}


@register_crawler(name="iranhotel", services={"hotel", "accommodation"})
class IranHotelCrawler(BaseCrawler):
    """
    Crawler adapter for Iran Hotel Online (https://www.iranhotelonline.com).
    Aggregates domestic hotels, hotel apartments, traditional boutique hotels,
    and eco-resorts across all Iranian provinces and cities.
    """

    provider_name: str = "iranhotel"
    supported_services = {"hotel", "accommodation"}
    is_cacheable: bool = False

    BASE_URL = "https://www.iranhotelonline.com/api/mvc"
    DEFAULT_TIMEOUT = 15.0

    def __init__(self, client: Optional[ResilientHttpClient] = None):
        self.client = client or ResilientHttpClient(timeout=self.DEFAULT_TIMEOUT)
        self._states_cities_cache: Optional[List[dict]] = None

    def _normalize_date_to_jalali(self, date_str: str) -> str:
        """
        Convert Gregorian date or Jalali with dashes to Jalali 'YYYY/MM/DD'.
        Example: '2026-10-07' -> '1405/07/15', '1405-07-15' -> '1405/07/15'
        """
        cleaned = date_str.strip().replace("-", "/")
        try:
            jalali_str = to_jalali(cleaned)
            return jalali_str.replace("-", "/")
        except Exception:
            return cleaned

    def _resolve_city_slug(self, city: str) -> str:
        """Resolve Persian or English city name to the slug used by IranHotelOnline."""
        clean = city.strip().lower()
        if clean in CITY_SLUG_MAP:
            return CITY_SLUG_MAP[clean]
        return clean

    # -------------------------------------------------------------------------
    # Hotel Search
    # -------------------------------------------------------------------------
    async def search_hotels(self, query: HotelSearchQuery) -> List[HotelResult]:
        """
        Search hotels in a given city with date range, star filters, and prices.
        Endpoint: GET /api/mvc/v1/search/filter
        """
        city_slug = self._resolve_city_slug(query.city)
        checkin_jalali = self._normalize_date_to_jalali(query.checkin_date)
        checkout_jalali = self._normalize_date_to_jalali(query.checkout_date)

        page_index = max(0, query.page - 1) if hasattr(query, "page") and query.page else 0

        params: Dict[str, Any] = {
            "HotelId": 0,
            "StateId": 0,
            "CityId": 0,
            "RegionId": 0,
            "DistrictId": 0,
            "ReferUrl": "iranlist",
            "NoRoom": query.rooms or 1,
            "Nights": 1,
            "Kind": "double",
            "Adult": query.adults or 2,
            "Child": 0,
            "Room": query.rooms or 1,
            "Sort": query.sort_by or "",
            "ShabIndex": 0,
            "SearchQuery": "",
            "type": 1,
            "StartDate": checkin_jalali,
            "EndDate": checkout_jalali,
            "PageIndex": page_index,
            "PageSize": 20,
            "isFirstRequest": page_index == 0,
            "CityName": city_slug,
        }

        # Star grade filter
        if query.stars:
            params["grades"] = str(query.stars)

        if query.min_price is not None:
            params["minPrice"] = query.min_price
        if query.max_price is not None:
            params["maxPrice"] = query.max_price

        url = f"{self.BASE_URL}/v1/search/filter"
        try:
            resp = await self.client.get(url, params=params)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_hotels(data, query)
        except Exception as e:
            logger.error(f"IranHotelOnline search_hotels failed for city='{query.city}': {e}")
            raise

    def _parse_hotels(self, data: dict, query: HotelSearchQuery) -> List[HotelResult]:
        results: List[HotelResult] = []
        cards = data.get("Cards", [])
        if not cards:
            return results

        scraped_at = datetime.utcnow().isoformat()

        for c in cards:
            card_data = c.get("CardData", {})
            if not card_data:
                continue

            hotel_id = str(card_data.get("Id", ""))
            hotel_name = card_data.get("HotelName", "")
            full_name = card_data.get("FullName") or hotel_name

            # Star rating
            star_obj = card_data.get("Star") or {}
            stars = star_obj.get("GradeId") if isinstance(star_obj, dict) else None

            # User score & reviews
            score_obj = card_data.get("Score") or {}
            user_rating = score_obj.get("ScoreNumber") if isinstance(score_obj, dict) else None
            reviews_count = score_obj.get("Total") if isinstance(score_obj, dict) else None

            # Address & coordinates
            addr_obj = card_data.get("Address") or {}
            address = addr_obj.get("Address") if isinstance(addr_obj, dict) else None
            lat = addr_obj.get("Lat") if isinstance(addr_obj, dict) else None
            lng = addr_obj.get("Long") if isinstance(addr_obj, dict) else None

            # Discount
            discount_obj = card_data.get("DiscountBalloon") or {}
            discount_pct = discount_obj.get("Discount") if isinstance(discount_obj, dict) else None

            # Thumbnail picture
            pictures = card_data.get("Pictures", [])
            thumbnail_url = None
            if pictures and isinstance(pictures, list):
                first_pic = pictures[0]
                thumbnail_url = first_pic.get("Webp") or first_pic.get("Jpg") or first_pic.get("ThumbnailUrl")

            # Starting price per night (in Iranian Rials)
            price_obj = card_data.get("Price") or {}
            iho_price = float(price_obj.get("IhoPrice") or 0.0)
            board_price = float(price_obj.get("BoardPrice") or 0.0)

            # PriceInfo
            price_amount = iho_price if iho_price > 0 else board_price
            price_info = PriceInfo(
                amount=price_amount,
                currency=Currency.IRR,
                formatted=f"{int(price_amount):,} ریال" if price_amount else "استعلام قیمت",
            )

            hotel_url = card_data.get("HotelUrl")

            hotel = HotelResult(
                id=f"iho_{hotel_id}",
                provider=ProviderInfo(name=self.provider_name, scraped_at=scraped_at),
                hotel_name=full_name,
                hotel_name_en=card_data.get("HotelForeignName"),
                stars=stars,
                user_rating=user_rating,
                address=address,
                thumbnail_url=thumbnail_url,
                min_price_per_night=price_info,
                rooms=[],
                latitude=float(lat) if lat else None,
                longitude=float(lng) if lng else None,
                reviews_count=reviews_count,
                discount_percent=float(discount_pct) if discount_pct else None,
                hotel_url=hotel_url,
            )
            results.append(hotel)

        return results

    # -------------------------------------------------------------------------
    # Room Inventory & Detailed Rates
    # -------------------------------------------------------------------------
    async def fetch_hotel_rooms(
        self,
        hotel_id: int,
        checkin_date: str,
        checkout_date: str,
    ) -> List[RoomOffer]:
        """
        Fetch all room types, bed capacities, meal plans, cancellation policies,
        and real-time rates for a specific hotel.
        Endpoint: POST /api/mvc/v1/hotelInfo/hotelRooms
        """
        checkin_jalali = self._normalize_date_to_jalali(checkin_date)
        checkout_jalali = self._normalize_date_to_jalali(checkout_date)

        url = f"{self.BASE_URL}/v1/hotelInfo/hotelRooms"
        payload = {
            "startDate": checkin_jalali,
            "hotelId": hotel_id,
            "endDate": checkout_jalali,
        }

        try:
            resp = await self.client.post(url, json_data=payload)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            return self._parse_room_offers(data)
        except Exception as e:
            logger.error(f"IranHotelOnline fetch_hotel_rooms failed for hotelId={hotel_id}: {e}")
            return []

    def _parse_room_offers(self, data: dict) -> List[RoomOffer]:
        offers: List[RoomOffer] = []
        room_data = data.get("room", {})
        containers = room_data.get("roomContainer", [])

        for c in containers:
            room_name = c.get("name", "اتاق")
            room_infos = c.get("roomInfos", [])
            for ri in room_infos:
                price_dict = ri.get("roomPrice", {}).get("price", {})
                iho_price = float(price_dict.get("ihoPrice") or 0.0)
                board_price = float(price_dict.get("boardPrice") or 0.0)

                cap = ri.get("roomCapacity", {})
                adult_cap = cap.get("adultCapacity", 2)
                extra_cap = cap.get("extraCapacity", 0)
                extra_price_val = cap.get("extraCapacityPrice")

                detail = ri.get("roomDetail", {}) or {}
                has_breakfast = detail.get("breakfast", False)
                is_cancellable = not detail.get("nonRefundable", False)

                extra_price_info = None
                if extra_price_val:
                    extra_price_info = PriceInfo(
                        amount=float(extra_price_val),
                        currency=Currency.IRR,
                        formatted=f"{int(extra_price_val):,} ریال",
                    )

                final_price = iho_price if iho_price > 0 else board_price
                offer = RoomOffer(
                    room_name=room_name,
                    capacity=adult_cap,
                    has_breakfast=has_breakfast,
                    is_cancellable=is_cancellable,
                    price_per_night=PriceInfo(
                        amount=final_price,
                        currency=Currency.IRR,
                        formatted=f"{int(final_price):,} ریال",
                    ),
                    total_price=PriceInfo(
                        amount=final_price,
                        currency=Currency.IRR,
                        formatted=f"{int(final_price):,} ریال",
                    ),
                    extra_capacity=extra_cap,
                    extra_price=extra_price_info,
                )
                offers.append(offer)

        return offers

    # -------------------------------------------------------------------------
    # Accommodation Search (Ecolodges, Hotel Apartments, Traditional Houses)
    # -------------------------------------------------------------------------
    async def search_accommodations(
        self,
        query: AccommodationSearchQuery,
    ) -> List[AccommodationResult]:
        """
        Search hotel apartments, suites, and eco-resorts on IranHotelOnline.
        Translates AccommodationSearchQuery into IranHotelOnline hotel search.
        """
        hotel_query = HotelSearchQuery(
            city=query.city,
            checkin_date=query.checkin_date,
            checkout_date=query.checkout_date,
            rooms=1,
            adults=query.guests,
            page=query.page,
        )
        hotels = await self.search_hotels(hotel_query)

        scraped_at = datetime.utcnow().isoformat()
        results: List[AccommodationResult] = []
        for h in hotels:
            residence = AccommodationResult(
                id=h.id,
                provider=ProviderInfo(name=self.provider_name, scraped_at=scraped_at),
                title=h.hotel_name,
                property_type="apartmenthotel" if "آپارتمان" in h.hotel_name else "hotel",
                city=query.city,
                capacity_standard=query.guests,
                capacity_max=query.guests + 2,
                bedrooms=1,
                rating=h.user_rating,
                reviews_count=h.reviews_count,
                price_per_night=PriceInfo(
                    amount=h.min_price_per_night.amount / 10,  # Convert Rials to Tomans for Accommodation schema
                    currency=Currency.IRT,
                    formatted=f"{int(h.min_price_per_night.amount / 10):,} تومان",
                ),
                thumbnail_url=h.thumbnail_url,
                amenities=[],
            )
            results.append(residence)

        return results

    # -------------------------------------------------------------------------
    # Location Metadata: Provinces & Cities
    # -------------------------------------------------------------------------
    async def _fetch_states_cities_tree(self) -> List[dict]:
        """Internal helper to fetch and memoize the full state & city hierarchy."""
        if self._states_cities_cache is not None:
            return self._states_cities_cache

        url = f"{self.BASE_URL}/reviews/getstatescities"
        try:
            resp = await self.client.get(url)
            data = resp.json() if hasattr(resp, "json") else resp
            if asyncio.iscoroutine(data):
                data = await data
            if isinstance(data, list):
                self._states_cities_cache = data
                return data
        except Exception as e:
            logger.error(f"Failed to fetch getstatescities from IranHotelOnline: {e}")

        return []

    async def get_provinces(self) -> List[ProvinceItem]:
        """Fetch list of all 40 Iranian provinces supported by IranHotelOnline."""
        tree = await self._fetch_states_cities_tree()
        provinces: List[ProvinceItem] = []
        for state in tree:
            state_id = str(state.get("StateId"))
            state_name = state.get("StateTitle", "")
            hotel_count = state.get("CountHotelsOfState", 0)
            provinces.append(
                ProvinceItem(
                    id=state_id,
                    slug=state_name.replace(" ", "-"),
                    name=state_name,
                    rooms_count=hotel_count,
                )
            )
        return provinces

    async def get_cities(self, province_id: Optional[str] = None) -> List[CityItem]:
        """
        Fetch cities, optionally filtered by parent province ID (e.g. '8' for Tehran, '11' for Khorasan).
        """
        tree = await self._fetch_states_cities_tree()
        cities: List[CityItem] = []

        for state in tree:
            current_state_id = str(state.get("StateId"))
            if province_id and current_state_id != str(province_id).strip():
                continue

            for c in (state.get("Cities") or []):
                cities.append(
                    CityItem(
                        id=str(c.get("CityId")),
                        slug=c.get("CityEnTitle", "").lower(),
                        name=c.get("CityTitle", ""),
                        province_id=current_state_id,
                        rooms_count=c.get("CountHotelsOfCity"),
                    )
                )

        return cities

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------
    async def health_check(self) -> bool:
        """Ping IranHotelOnline API gateway to verify connectivity."""
        try:
            url = f"{self.BASE_URL}/hotelInfo/suggest"
            resp = await self.client.get(url, params={"query": "تهران", "take": 1})
            return resp.status_code == 200
        except Exception:
            return False
