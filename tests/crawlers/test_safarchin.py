import pytest
from unittest.mock import AsyncMock, patch
from app.crawlers.safarchin.crawler import SafarchinCrawler
from app.crawlers.safarchin.airports import find_airport, resolve_route, AIRPORTS
from app.crawlers.safarchin.parser import parse_flights_html, parse_calendar_json
from app.schemas.flight import FlightSearchQuery
from app.schemas.transport import TransportSearchQuery

MOCK_FLIGHT_HTML = """
<div id="tab_record">
    <input type="hidden" id="all_record" value="2" />
    <div class="resu " data="0" rel="تهران" rev="مشهد" atba-data="0">
        <div class="price ">
            <span>9,312</span>
            <div class="icon11">اکونومی</div>
        </div>
        <div class="date">
            04:30
            <i class="icon icon-time"></i>
        </div>
        <div class="user">
            <span class="icon icon-seat"></span>
            9+
        </div>
        <div class="code">
            <div class="info_parvaz efitooltip_bg" tabindex="-1">
                <div class="mkfcol1">
                    <img class="plan_icon" src="https://cdn.agent724.ir/template/backc118/images/airline/avaair_ok.png"/>
                    <strong>تهران-مشهد </strong><br><strong class='airline_name'>آوا ایر</strong><br/>
                </div>
                <div class='mkfcol2'>
                    <strong>شماره پرواز: </strong>7702<br>
                    <strong>نوع هواپیما: </strong><span class='airline_type' rel='b737'> بوئینگ</span><br>
                    <strong>ظرفیت :</strong> ۱۳۰ تا ۱۵۰ نفر<br>
                    <strong>بار مجاز: </strong>20 KG<br>
                    <strong>قیمت کودک: </strong>92,903,000<br>
                    <strong>قیمت نوزاد: </strong>20,000,000<br>
                </div>
                <div class='mkfcol3'>
                    <strong>کلاس پروازی: </strong>Y<br>
                    <strong>قوانین استردادی</strong>:<br>
                    <span class="esterdad_law">تا 12 ظهر روز قبل از پرواز 30 درصد جریمه</span>
                </div>
            </div>
            <span class="code_inn">7702</span>
            <div class="plan_icon_bg plan_icon">
                <img class="plan_icon" src="https://cdn.agent724.ir/template/backc118/images/airline/avaair_ok.png" rel="avaair_ok.png">
            </div>
        </div>
        <div class="select" rel="9,312,300*5*5|9,415,000*5*5">
            <a class="reserve_online" id="446" rel="756415" rev="8" data="0" target="_blank" title="Y">خرید</a>
        </div>
    </div><!--resu-->
    <div class="resu " data="0" rel="تهران" rev="مشهد" atba-data="0">
        <div class="price ">
            <span>12,323</span>
            <div class="icon11">سیستمی</div>
        </div>
        <div class="date">
            22:40
            <i class="icon icon-time"></i>
        </div>
        <div class="user">
            <span class="icon icon-seat"></span>
            4
        </div>
        <div class="code">
            <div class="info_parvaz efitooltip_bg" tabindex="-1">
                <div class="mkfcol1">
                    <strong class='airline_name'>ماهان</strong><br/>
                </div>
                <div class='mkfcol2'>
                    <strong>شماره پرواز: </strong>1037<br>
                    <strong>نوع هواپیما: </strong><span class='airline_type'> ایرباس</span><br>
                    <strong>بار مجاز: </strong>30 KG<br>
                    <strong>قیمت بزرگسال: </strong>123,230,000<br>
                </div>
                <div class='mkfcol3'>
                    <strong>کلاس پروازی: </strong>C<br>
                </div>
            </div>
            <span class="code_inn">1037</span>
            <div class="plan_icon_bg plan_icon">
                <img class="plan_icon" src="https://cdn.agent724.ir/template/backc118/images/airline/Mahan_ok.png" rel="Mahan_ok.png">
            </div>
        </div>
        <div class="select" rel="12,323,000*4*8">
            <a class="reserve_online" id="446" rel="756416" rev="8" data="0" target="_blank" title="C">خرید</a>
        </div>
    </div><!--resu-->
</div>
"""

MOCK_CALENDAR_JSON = {
    "from": "تهران",
    "to": "مشهد",
    "result": [
        {
            "price": "9,312<span>تومان</span>",
            "date_flight": "07/14",
            "type_flight": "5",
            "week": "سه شنبه",
            "link": "Ticket-Tehran-Mashhad.html?t=1405-07-14",
        },
        {
            "price": "8,712<span>تومان</span>",
            "date_flight": "07/15",
            "type_flight": "5",
            "week": "چهارشنبه",
            "link": "Ticket-Tehran-Mashhad.html?t=1405-07-15",
        }
    ],
    "ndate": 1,
    "ldate": -1,
}

def test_airport_resolver():
    """Verify IATA, Persian, English, and 5-digit ID lookups."""
    thr = find_airport("THR")
    assert thr is not None
    assert thr.slug == "Tehran"
    assert thr.id == "10000"
    
    mhd = find_airport("مشهد")
    assert mhd is not None
    assert mhd.slug == "Mashhad"
    assert mhd.id == "10001"
    
    kih = find_airport("KIH")
    assert kih is not None
    assert kih.slug == "Kish"
    
    orig, dest = resolve_route("THR", "MHD")
    assert orig.slug == "Tehran"
    assert dest.slug == "Mashhad"

    with pytest.raises(ValueError):
        resolve_route("NON_EXISTING_XYZ", "MHD")

def test_parse_flights_html():
    """Verify HTML flight extraction logic."""
    query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="1405-07-14")
    results = parse_flights_html(
        html=MOCK_FLIGHT_HTML,
        query=query,
        orig_slug="Tehran",
        dest_slug="Mashhad",
        depart_jalali="1405-07-14"
    )
    
    assert len(results) == 2
    
    # Flight 1: Ava Air
    f1 = results[0]
    assert f1.provider.name == "safarchin"
    assert f1.price.amount == 9312300.0
    assert f1.available_seats == 9
    assert f1.is_charter is True
    assert f1.outbound[0].airline_name == "آوا ایر"
    assert f1.outbound[0].flight_number == "7702"
    assert f1.outbound[0].aircraft == "بوئینگ"
    assert f1.outbound[0].departure_time == "04:30"
    assert f1.outbound[0].cabin_class == "economy"
    
    # Flight 2: Mahan Air
    f2 = results[1]
    assert f2.price.amount == 12323000.0
    assert f2.available_seats == 4
    assert f2.is_charter is False  # Systemic
    assert f2.outbound[0].airline_name == "ماهان"
    assert f2.outbound[0].flight_number == "1037"
    assert f2.outbound[0].cabin_class == "business"

def test_parse_calendar_json():
    """Verify 15-day price calendar parsing."""
    parsed = parse_calendar_json(MOCK_CALENDAR_JSON, origin="Tehran", destination="Mashhad")
    assert parsed["origin"] == "Tehran"
    assert parsed["destination"] == "Mashhad"
    assert parsed["has_next_page"] is True
    assert parsed["next_page"] == 1
    assert len(parsed["calendar"]) == 2
    
    day1 = parsed["calendar"][0]
    assert day1["shamsi_date"] == "1405-07-14"
    assert day1["day_of_week"] == "سه شنبه"
    assert day1["min_price_tomans"] == 9312000.0
    assert day1["is_available"] is True

@pytest.mark.asyncio
async def test_safarchin_search_flights_mocked():
    """Verify SafarchinCrawler.search_flights with mocked client response."""
    crawler = SafarchinCrawler()
    
    mock_resp = AsyncMock()
    mock_resp.text = MOCK_FLIGHT_HTML
    mock_resp.status_code = 200
    
    with patch.object(crawler.client, "post", return_value=mock_resp) as mock_post:
        query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="1405-07-14")
        results = await crawler.search_flights(query)
        
        assert len(results) == 2
        assert mock_post.called
        call_url = mock_post.call_args[1]["url"]
        assert "Ticket-Tehran-Mashhad.html?t=1405-07-14" in call_url

@pytest.mark.asyncio
async def test_safarchin_search_calendar_mocked():
    """Verify SafarchinCrawler.search_calendar with mocked client response."""
    crawler = SafarchinCrawler()
    
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value=MOCK_CALENDAR_JSON)
    mock_resp.status_code = 200
    
    with patch.object(crawler.client, "post", return_value=mock_resp) as mock_post:
        result = await crawler.search_calendar(origin="THR", destination="MHD", page=1)
        
        assert result["has_next_page"] is True
        assert len(result["calendar"]) == 2
        call_data = mock_post.call_args[1]["data"]
        assert call_data["from"] == "10000"
        assert call_data["to"] == "10001"
        assert call_data["pdate"] == "1"

@pytest.mark.asyncio
async def test_safarchin_error_retry():
    """Verify crawler handles and propagates network failure after retries."""
    crawler = SafarchinCrawler()
    
    with patch.object(crawler.client, "post", side_effect=Exception("Connection refused")):
        query = FlightSearchQuery(origin="THR", destination="MHD", depart_date="1405-07-14")
        with pytest.raises(Exception) as exc_info:
            await crawler.search_flights(query)
        assert "Connection refused" in str(exc_info.value)
