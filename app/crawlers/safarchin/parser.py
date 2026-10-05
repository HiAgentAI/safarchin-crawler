import re
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.schemas.flight import FlightSearchQuery, FlightResult, FlightSegment
from app.schemas.common import PriceInfo, Currency, ProviderInfo
from app.utils.calendar import to_gregorian, to_jalali

logger = logging.getLogger(__name__)

def _clean_price(price_str: Optional[str]) -> Optional[float]:
    """Clean numeric price string by removing commas, spaces, and non-digits."""
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d]", "", price_str)
    return float(cleaned) if cleaned else None

def parse_flights_html(
    html: str,
    query: FlightSearchQuery,
    orig_slug: str,
    dest_slug: str,
    depart_jalali: str,
    provider_name: str = "safarchin",
    base_url: str = "http://safarchin.ir"
) -> List[FlightResult]:
    """
    Parses Safarchin flight search HTML response into structured FlightResult schemas.
    """
    results: List[FlightResult] = []
    
    # Split into flight blocks. Each flight card begins with <div class="resu
    blocks = [b for b in html.split('<div class="resu ') if 'price' in b and 'plan_icon' in b]
    
    depart_gregorian = to_gregorian(depart_jalali)
    
    for idx, block in enumerate(blocks):
        try:
            # 1. Airline Name
            airline_m = re.search(r"<strong class='airline_name'>([^<]+)</strong>", block)
            airline = airline_m.group(1).strip() if airline_m else "نامشخص"
            
            # 2. Flight Number
            fn_m = re.search(r"<strong>شماره پرواز:\s*</strong>([^<]+)<", block)
            if not fn_m:
                fn_m = re.search(r'<span class="code_inn">([^<]+)</span>', block)
            flight_number = fn_m.group(1).strip() if fn_m else f"SF-{idx+1}"
            
            # 3. Aircraft Model
            ac_m = re.search(r"<span class='airline_type'[^>]*>\s*([^<]+)</span>", block)
            aircraft = ac_m.group(1).strip() if ac_m else None
            
            # 4. Departure & Arrival Times
            time_m = re.search(r'<div class="date">\s*([0-9]{2}:[0-9]{2})', block)
            dep_time = time_m.group(1).strip() if time_m else "00:00"
            
            # Estimate arrival time (+1h 30m typical domestic flight if not explicitly stated)
            try:
                t_obj = datetime.strptime(dep_time, "%H:%M")
                arr_time = (t_obj + timedelta(hours=1, minutes=30)).strftime("%H:%M")
            except Exception:
                arr_time = dep_time
                
            # 5. Available Seats
            seat_m = re.search(r'<div class="user">\s*(?:<span[^>]*></span>)?\s*([0-9]+)\+?', block)
            seats: Optional[int] = None
            if seat_m:
                try:
                    seats = int(seat_m.group(1))
                except ValueError:
                    seats = 9
            else:
                seats = 9 if "9+" in block else 1
                
            # 6. Pricing
            # Check select tag rel (contains detailed prices, e.g., 9,312,300*5*5)
            select_m = re.search(r'<div class="select"[^>]*rel="([^"]+)"', block)
            adult_price: Optional[float] = None
            if select_m:
                first_tier = select_m.group(1).split("|")[0]
                price_part = first_tier.split("*")[0].strip()
                adult_price = _clean_price(price_part)
                
            # Fallback to card price (in thousands of Tomans, e.g., 9,312 -> 9,312,000)
            if not adult_price:
                card_p = re.search(r'<div class="price\s*[^"]*"[^>]*>\s*<span\s*>([0-9,]+)</span>', block)
                if card_p:
                    card_val = _clean_price(card_p.group(1))
                    if card_val:
                        adult_price = card_val * 1000.0
                        
            if not adult_price:
                # Fallback to adult price label
                p_label = re.search(r"<strong>قیمت بزرگسال:\s*</strong>([0-9,]+)", block)
                if p_label:
                    # In Rials -> convert to Tomans
                    adult_price = (_clean_price(p_label.group(1)) or 0) / 10.0
                    
            if not adult_price:
                adult_price = 0.0
                
            price_info = PriceInfo(
                amount=adult_price,
                currency=Currency.IRT,
                formatted=f"{int(adult_price):,} تومان"
            )
            
            # 7. Cabin Class & Booking Class
            class_m = re.search(r"<strong>کلاس پروازی:\s*</strong>([A-Z0-9]+)", block)
            cabin_code = class_m.group(1).strip() if class_m else "Y"
            
            cabin_class = "economy"
            if "بیزینس" in block or cabin_code in ("C", "J"):
                cabin_class = "business"
            elif "فرست" in block or cabin_code in ("F", "A"):
                cabin_class = "first"
                
            # 8. Flight Type (Charter vs Systemic)
            is_charter = True
            if "سیستمی" in block:
                is_charter = False
            elif "چارتری" in block:
                is_charter = True
                
            # 9. Baggage Allowance
            baggage_m = re.search(r"<strong>بار مجاز:\s*</strong>([^<]+)<", block)
            baggage = baggage_m.group(1).strip() if baggage_m else "20 KG"
            
            # 10. Direct Deep Link
            deep_link = f"{base_url}/Ticket-{orig_slug}-{dest_slug}.html?t={depart_jalali}"
            
            segment = FlightSegment(
                airline_name=airline,
                airline_code=None,
                flight_number=flight_number,
                aircraft=aircraft,
                origin_code=query.origin.upper(),
                destination_code=query.destination.upper(),
                departure_time=dep_time,
                arrival_time=arr_time,
                departure_date=depart_gregorian,
                arrival_date=depart_gregorian,
                cabin_class=cabin_class,
                baggage=baggage,
            )
            
            result_id = f"safarchin_{flight_number}_{dep_time.replace(':', '')}_{idx}"
            
            results.append(FlightResult(
                id=result_id,
                provider=ProviderInfo(
                    name=provider_name,
                    deep_link=deep_link,
                    scraped_at=datetime.utcnow().isoformat(),
                ),
                is_charter=is_charter,
                price=price_info,
                available_seats=seats,
                outbound=[segment],
                inbound=None,
            ))
            
        except Exception as e:
            logger.warning(f"Failed to parse Safarchin flight block {idx}: {e}")
            continue
            
    return results

def parse_calendar_json(raw_json: dict, origin: str, destination: str) -> dict:
    """
    Parses the 15-day price matrix JSON returned by get_query.html.
    """
    items = []
    current_year = 1405  # Standard Jalali year base
    
    for entry in raw_json.get("result", []):
        price_raw = entry.get("price", "")
        # Remove HTML tags (e.g., <span>تومان</span>)
        price_cleaned = re.sub(r"<[^>]+>", "", price_raw).strip()
        price_num = _clean_price(price_cleaned)
        
        # In calendar response, prices are in thousands of Tomans (e.g. 9,312 -> 9,312,000 Tomans)
        price_tomans = (price_num * 1000.0) if price_num and price_num < 100000 else price_num
        
        link = entry.get("link", "")
        shamsi_date = None
        date_m = re.search(r"t=([0-9]{4}-[0-9]{2}-[0-9]{2})", link)
        if date_m:
            shamsi_date = date_m.group(1)
        else:
            df = entry.get("date_flight", "")
            if "/" in df:
                shamsi_date = f"{current_year}-{df.replace('/', '-')}"
                
        gregorian_date = to_gregorian(shamsi_date) if shamsi_date else None
        
        items.append({
            "shamsi_date": shamsi_date,
            "gregorian_date": gregorian_date,
            "day_of_week": entry.get("week"),
            "min_price_tomans": price_tomans,
            "formatted_price": f"{int(price_tomans):,} تومان" if price_tomans else "ناموجود",
            "is_available": price_tomans is not None,
            "booking_link": f"http://safarchin.ir/{link}" if link else None,
        })
        
    return {
        "origin": origin,
        "destination": destination,
        "from_title": raw_json.get("from"),
        "to_title": raw_json.get("to"),
        "has_next_page": raw_json.get("ndate", -1) > 0,
        "next_page": raw_json.get("ndate"),
        "prev_page": raw_json.get("ldate"),
        "calendar": items,
    }
