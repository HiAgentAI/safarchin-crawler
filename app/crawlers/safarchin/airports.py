# Auto-generated Safarchin airport and city dictionary
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class AirportInfo:
    id: str
    slug: str
    iata: str
    persian_name: str
    english_name: str

AIRPORTS: List[AirportInfo] = [
    AirportInfo(id='10000', slug='Tehran', iata='THR', persian_name='تهران', english_name='Tehran'),
    AirportInfo(id='10001', slug='Mashhad', iata='MHD', persian_name='مشهد', english_name='Mashhad'),
    AirportInfo(id='10002', slug='Isfahan', iata='IFN', persian_name='اصفهان', english_name='Isfahan'),
    AirportInfo(id='10003', slug='Kish', iata='KIH', persian_name='کیش', english_name='Kish'),
    AirportInfo(id='10004', slug='Ahwaz', iata='AWZ', persian_name='اهواز', english_name='Ahwaz'),
    AirportInfo(id='10005', slug='Shiraz', iata='SYZ', persian_name='شیراز', english_name='Shiraz'),
    AirportInfo(id='10006', slug='Tabriz', iata='TBZ', persian_name='تبریز', english_name='Tabriz'),
    AirportInfo(id='10008', slug='Hamedan', iata='HDM', persian_name='همدان', english_name='Hamedan'),
    AirportInfo(id='10009', slug='Asalooye', iata='PGU', persian_name='عسلویه', english_name='Asalooye'),
    AirportInfo(id='10010', slug='Bandar Abass', iata='BND', persian_name='بندرعباس', english_name='Bandar Abass'),
    AirportInfo(id='10011', slug='Kerman', iata='KER', persian_name='کرمان', english_name='Kerman'),
    AirportInfo(id='10012', slug='Gheshm', iata='GSM', persian_name='قشم', english_name='Gheshm'),
    AirportInfo(id='10013', slug='Noshahr', iata='NSH', persian_name='نوشهر', english_name='Noshahr'),
    AirportInfo(id='10018', slug='Dubai', iata='DXB', persian_name='دبی', english_name='Dubai'),
    AirportInfo(id='10368', slug='Abu Dhabi', iata='AUH', persian_name='ابوظبی', english_name='Abu Dhabi'),
    AirportInfo(id='10015', slug='Bushehr', iata='BUZ', persian_name='بوشهر', english_name='Bushehr'),
    AirportInfo(id='10366', slug='Dubai_Al Maktoum', iata='DWC', persian_name='دبی', english_name='Dubai_Al Maktoum'),
    AirportInfo(id='10016', slug='Sari', iata='SRY', persian_name='ساری', english_name='Sari'),
    AirportInfo(id='10355', slug='Istanbul_All', iata='همه', persian_name='استانبول', english_name='Istanbul_All'),
    AirportInfo(id='10358', slug='Antalya_All', iata='همه', persian_name='آنتالیا', english_name='Antalya_All'),
    AirportInfo(id='10362', slug='Dubai_All', iata='همه', persian_name='دبی', english_name='Dubai_All'),
    AirportInfo(id='10017', slug='Istanbul', iata='IST', persian_name='استانبول', english_name='Istanbul'),
    AirportInfo(id='10354', slug='Istanbul_Sabiha', iata='SAW', persian_name='استانبول(سبیها)', english_name='Istanbul_Sabiha'),
    AirportInfo(id='10014', slug='Ardabil', iata='ADU', persian_name='اردبیل', english_name='Ardabil'),
    AirportInfo(id='10019', slug='Yerevan', iata='EVN', persian_name='ایروان', english_name='Yerevan'),
    AirportInfo(id='10020', slug='Bangkok', iata='BKK', persian_name='بانکوک', english_name='Bangkok'),
    AirportInfo(id='10021', slug='Kuala Lumpur', iata='KUL', persian_name='کوالالامپور', english_name='Kuala Lumpur'),
    AirportInfo(id='10022', slug='Najaf', iata='NJF', persian_name='نجف', english_name='Najaf'),
    AirportInfo(id='10364', slug='Kirkuk', iata='KIK', persian_name='کرکوک', english_name='Kirkuk'),
    AirportInfo(id='10023', slug='Baghdad', iata='BGW', persian_name='بغداد', english_name='Baghdad'),
    AirportInfo(id='10024', slug='Rasht', iata='RAS', persian_name='رشت', english_name='Rasht'),
    AirportInfo(id='10025', slug='Dezful', iata='DEF', persian_name='دزفول', english_name='Dezful'),
    AirportInfo(id='10026', slug='Erbil', iata='EBL', persian_name='اربیل', english_name='Erbil'),
    AirportInfo(id='10027', slug='Yazd', iata='AZD', persian_name='یزد', english_name='Yazd'),
    AirportInfo(id='10028', slug='Urmia', iata='OMH', persian_name='ارومیه', english_name='Urmia'),
    AirportInfo(id='10029', slug='Mahshar', iata='MRX', persian_name='ماهشهر', english_name='Mahshar'),
    AirportInfo(id='10030', slug='Abadan', iata='ABD', persian_name='آبادان', english_name='Abadan'),
    AirportInfo(id='10031', slug='Zanjan', iata='JWN', persian_name='زنجان', english_name='Zanjan'),
    AirportInfo(id='10032', slug='Shahrekord', iata='CQD', persian_name='شهرکرد', english_name='Shahrekord'),
    AirportInfo(id='10033', slug='Gorgan', iata='GBT', persian_name='گرگان', english_name='Gorgan'),
    AirportInfo(id='10034', slug='Sulaymaniyah', iata='ISU', persian_name='سلیمانیه', english_name='Sulaymaniyah'),
    AirportInfo(id='10035', slug='Antalya', iata='AYT', persian_name='آنتالیا', english_name='Antalya'),
    AirportInfo(id='10359', slug='Antalya_Isparta', iata='ISE', persian_name='اسپارتا', english_name='Antalya_Isparta'),
    AirportInfo(id='10036', slug='Bodrum_Kusadasi', iata='BJV', persian_name='بدروم / کوش آداسی', english_name='Bodrum_Kusadasi'),
    AirportInfo(id='10037', slug='Basra', iata='BSR', persian_name='بصره', english_name='Basra'),
    AirportInfo(id='10038', slug='Tbilisi', iata='TBS', persian_name='تفلیس', english_name='Tbilisi'),
    AirportInfo(id='10039', slug='Beirut', iata='BEY', persian_name='بیروت', english_name='Beirut'),
    AirportInfo(id='10040', slug='Zahedan', iata='ZAH', persian_name='زاهدان', english_name='Zahedan'),
    AirportInfo(id='10042', slug='Bojnourd', iata='BJB', persian_name='بجنورد', english_name='Bojnourd'),
    AirportInfo(id='10043', slug='Ilam', iata='IIL', persian_name='ایلام', english_name='Ilam'),
    AirportInfo(id='10045', slug='Ankara', iata='ESB', persian_name='آنکارا', english_name='Ankara'),
    AirportInfo(id='10050', slug='Kuwait', iata='KWI', persian_name='کویت', english_name='Kuwait'),
    AirportInfo(id='10075', slug='Khoramabad', iata='KHD', persian_name='خرم اباد', english_name='Khoramabad'),
    AirportInfo(id='10081', slug='Chahbahar', iata='ZBR', persian_name='چابهار', english_name='Chahbahar'),
    AirportInfo(id='10007', slug='Kermanshah', iata='KSH', persian_name='کرمانشاه', english_name='Kermanshah'),
    AirportInfo(id='10166', slug='Zabol', iata='ACZ', persian_name='زابل', english_name='Zabol'),
    AirportInfo(id='10167', slug='Tabas', iata='TCX', persian_name='طبس', english_name='Tabas'),
    AirportInfo(id='10179', slug='Guangzhou', iata='CAN', persian_name='گوانجو', english_name='Guangzhou'),
    AirportInfo(id='10183', slug='Iranshar', iata='IHR', persian_name='ایرانشهر', english_name='Iranshar'),
    AirportInfo(id='10184', slug='Bam', iata='BXR', persian_name='بم', english_name='Bam'),
    AirportInfo(id='10185', slug='BandarLenge', iata='BDH', persian_name='بندرلنگه', english_name='BandarLenge'),
    AirportInfo(id='10186', slug='Jam', iata='KNR', persian_name='جم', english_name='Jam'),
    AirportInfo(id='10187', slug='Khark', iata='KHK', persian_name='خارک', english_name='Khark'),
    AirportInfo(id='10188', slug='Ramsar', iata='RZR', persian_name='رامسر', english_name='Ramsar'),
    AirportInfo(id='10189', slug='Rafsanjan', iata='RJN', persian_name='رفسنجان', english_name='Rafsanjan'),
    AirportInfo(id='10190', slug='Sanandaj', iata='SDG', persian_name='سنندج', english_name='Sanandaj'),
    AirportInfo(id='10191', slug='Sabzevar', iata='AFZ', persian_name='سبزوار', english_name='Sabzevar'),
    AirportInfo(id='10192', slug='Syrjan', iata='SYJ', persian_name='سیرجان', english_name='Syrjan'),
    AirportInfo(id='10193', slug='Ghachsaran', iata='GCH', persian_name='گچساران', english_name='Ghachsaran'),
    AirportInfo(id='10194', slug='Lar', iata='LRR', persian_name='لارستان', english_name='Lar'),
    AirportInfo(id='10195', slug='Lamard', iata='LFM', persian_name='لامرد', english_name='Lamard'),
    AirportInfo(id='10196', slug='Yasooj', iata='YES', persian_name='یاسوج', english_name='Yasooj'),
    AirportInfo(id='10199', slug='Birjand', iata='XBJ', persian_name='بیرجند', english_name='Birjand'),
    AirportInfo(id='10200', slug='Arjan', iata='ECN', persian_name='ارجان (قبرس)', english_name='Arjan'),
    AirportInfo(id='10201', slug='Alanya', iata='GZP', persian_name='آلانیا (ترکیه)', english_name='Alanya'),
    AirportInfo(id='10203', slug='Arak', iata='AJK', persian_name='اراک', english_name='Arak'),
    AirportInfo(id='10204', slug='Kabul', iata='KBL', persian_name='کابل', english_name='Kabul'),
    AirportInfo(id='10205', slug='Herat', iata='HEA', persian_name='هرات', english_name='Herat'),
    AirportInfo(id='10206', slug='Mazar Sharif', iata='MZR', persian_name='مزارشریف', english_name='Mazar Sharif'),
    AirportInfo(id='10207', slug='Kandahar', iata='KDH', persian_name='قندهار', english_name='Kandahar'),
    AirportInfo(id='10209', slug='Maragheh', iata='ACP', persian_name='مراغه', english_name='Maragheh'),
    AirportInfo(id='10210', slug='Bishkek', iata='FRU', persian_name='بیشکک', english_name='Bishkek'),
    AirportInfo(id='10217', slug='Shanghai', iata='PVG', persian_name='شانگهای', english_name='Shanghai'),
    AirportInfo(id='10373', slug='Shenzhen', iata='SZX', persian_name='شنژن', english_name='Shenzhen'),
    AirportInfo(id='10218', slug='Peking', iata='PEK', persian_name='پکن', english_name='Peking'),
    AirportInfo(id='10227', slug='COLOMBO', iata='CMB', persian_name='کلمبو', english_name='COLOMBO'),
    AirportInfo(id='10228', slug='Ghazvin', iata='GZW', persian_name='قزوین', english_name='Ghazvin'),
    AirportInfo(id='10233', slug='Hamburg', iata='HAM', persian_name='هامبورگ', english_name='Hamburg'),
    AirportInfo(id='10234', slug='DEHLI', iata='DEL', persian_name='دهلی', english_name='DEHLI'),
    AirportInfo(id='10236', slug='Bahrein', iata='BAH', persian_name='بحرین', english_name='Bahrein'),
    AirportInfo(id='10237', slug='Khoy', iata='KHY', persian_name='خوی', english_name='Khoy'),
    AirportInfo(id='10238', slug='Damascus', iata='DAM', persian_name='دمشق', english_name='Damascus'),
    AirportInfo(id='10239', slug='Dushanbe', iata='DYU', persian_name='دوشنبه', english_name='Dushanbe'),
    AirportInfo(id='10240', slug='Dubai_Sharjeh', iata='SHJ', persian_name='شارجه_دبی', english_name='Dubai_Sharjeh'),
    AirportInfo(id='10241', slug='Shahroud', iata='RUD', persian_name='شاهرود', english_name='Shahroud'),
    AirportInfo(id='10280', slug='Jiroft', iata='JYR', persian_name='جیروفت', english_name='Jiroft'),
    AirportInfo(id='10357', slug='Trabzon', iata='TZX', persian_name='ترابزون', english_name='Trabzon'),
    AirportInfo(id='10282', slug='BAKU', iata='GYD', persian_name='باکو', english_name='BAKU'),
    AirportInfo(id='10356', slug='Nakhchivan', iata='NAJ', persian_name='نخجوان', english_name='Nakhchivan'),
    AirportInfo(id='10283', slug='Izmir', iata='ADB', persian_name='ازمیر', english_name='Izmir'),
    AirportInfo(id='10284', slug='Kashan', iata='KKS', persian_name='کاشان', english_name='Kashan'),
    AirportInfo(id='10285', slug='Astrakhan', iata='ASF', persian_name='آستراخان(روسیه)', english_name='Astrakhan'),
    AirportInfo(id='10353', slug='Moscow_All', iata='همه', persian_name='مسکو', english_name='Moscow_All'),
    AirportInfo(id='10287', slug='Moscow_Vnukovo', iata='VKO', persian_name='مسکو', english_name='Moscow_Vnukovo'),
    AirportInfo(id='10288', slug='Varna', iata='VAR', persian_name='وارنا(بلغارستان)', english_name='Varna'),
    AirportInfo(id='10363', slug='Moscow_Domodedovo', iata='DME', persian_name='مسکو', english_name='Moscow_Domodedovo'),
    AirportInfo(id='10289', slug='Saint Petersburg', iata='LED', persian_name='سنت پترزبورگ', english_name='Saint Petersburg'),
    AirportInfo(id='10372', slug='Sochi', iata='AER', persian_name='سوچی', english_name='Sochi'),
    AirportInfo(id='10290', slug='Batumi', iata='BUS', persian_name='باتومی', english_name='Batumi'),
    AirportInfo(id='10291', slug='Almaty', iata='ALA', persian_name='آلماتی(قزاقستان)', english_name='Almaty'),
    AirportInfo(id='10360', slug='Aktau', iata='SCO', persian_name='آکتائو( آق تائو)', english_name='Aktau'),
    AirportInfo(id='10367', slug='Samarkand', iata='SKD', persian_name='سمرقند', english_name='Samarkand'),
    AirportInfo(id='10292', slug='Kalaleh', iata='KLM', persian_name='کلاله', english_name='Kalaleh'),
    AirportInfo(id='10293', slug='Antalya_Denizli', iata='DNZ', persian_name='دنیزلی', english_name='Antalya_Denizli'),
    AirportInfo(id='10295', slug='Muscat', iata='MCT', persian_name='مسقط', english_name='Muscat'),
    AirportInfo(id='10297', slug='Milan', iata='MXP', persian_name='میلان', english_name='Milan'),
    AirportInfo(id='10298', slug='Cologne', iata='CGN', persian_name='کلن آلمان', english_name='Cologne'),
    AirportInfo(id='10299', slug='Amsterdam', iata='AMS', persian_name='آمستردام', english_name='Amsterdam'),
    AirportInfo(id='10300', slug='Vienna', iata='VIE', persian_name='وین', english_name='Vienna'),
    AirportInfo(id='10369', slug='Gonabad', iata='MDN', persian_name='گناباد', english_name='Gonabad'),
    AirportInfo(id='10370', slug='Saravan', iata='SAR', persian_name='سراوان', english_name='Saravan'),
    AirportInfo(id='10371', slug='Saqqez', iata='TQZ', persian_name='سقز', english_name='Saqqez'),
    AirportInfo(id='10301', slug='Rome', iata='FCO', persian_name='رم ایتالیا', english_name='Rome'),
    AirportInfo(id='10303', slug='Karachi', iata='KHI', persian_name='کراچی', english_name='Karachi'),
    AirportInfo(id='10304', slug='Paris', iata='CDG', persian_name='پاریس', english_name='Paris'),
    AirportInfo(id='10305', slug='London Heathrow', iata='LHR', persian_name='هیترو لندن', english_name='London Heathrow'),
    AirportInfo(id='10361', slug='Rimini_Italy', iata='RMI', persian_name='ریمینی(ایتالیا)', english_name='Rimini_Italy'),
    AirportInfo(id='10306', slug='Frankfurt', iata='FRA', persian_name='فرانکفورت', english_name='Frankfurt'),
    AirportInfo(id='10308', slug='Dusseldorf', iata='DUS', persian_name='دوسلدورف', english_name='Dusseldorf'),
    AirportInfo(id='10309', slug='Munich', iata='MUC', persian_name='مونیخ', english_name='Munich'),
    AirportInfo(id='10310', slug='Maku', iata='IMQ', persian_name='ماکو', english_name='Maku'),
    AirportInfo(id='10312', slug='Lahore', iata='LHE', persian_name='لاهور', english_name='Lahore'),
    AirportInfo(id='10313', slug='Bruxelles', iata='BRU', persian_name='بروکسل', english_name='Bruxelles'),
    AirportInfo(id='10314', slug='Nasiriyah', iata='XNH', persian_name='ناصریه', english_name='Nasiriyah'),
    AirportInfo(id='10315', slug='Bali', iata='DPS', persian_name='بالی', english_name='Bali'),
    AirportInfo(id='10316', slug='Amman', iata='AMM', persian_name='عمان', english_name='Amman'),
    AirportInfo(id='10317', slug='Islamabad', iata='ISB', persian_name='اسلام آباد', english_name='Islamabad'),
    AirportInfo(id='10318', slug='Belgrade', iata='BEG', persian_name='بلگراد', english_name='Belgrade'),
    AirportInfo(id='10319', slug='Jahrom', iata='JAR', persian_name='جهرم', english_name='Jahrom'),
    AirportInfo(id='10320', slug='PARSABAD Moghan', iata='PFQ', persian_name='پارس آبادمغان', english_name='PARSABAD Moghan'),
    AirportInfo(id='10321', slug='Doha', iata='DOH', persian_name='دوحه', english_name='Doha'),
    AirportInfo(id='10322', slug='Mumbai', iata='BOM', persian_name='بمبئی', english_name='Mumbai'),
    AirportInfo(id='10323', slug='Kiev Zhuliany', iata='IEV', persian_name='کیف اوکراین', english_name='Kiev Zhuliany'),
    AirportInfo(id='10324', slug='Stockholm', iata='ARN', persian_name='استکهلم', english_name='Stockholm'),
    AirportInfo(id='10325', slug='Larnaca', iata='LCA', persian_name='لارناکا', english_name='Larnaca'),
    AirportInfo(id='10326', slug='Gothenburg', iata='GOT', persian_name='گوتنبرگ', english_name='Gothenburg'),
    AirportInfo(id='10327', slug='Kazan', iata='KZN', persian_name='کازان', english_name='Kazan'),
    AirportInfo(id='10328', slug='Karaj_Tehran', iata='PYK', persian_name='پیام کرج(تهران)', english_name='Karaj_Tehran'),
    AirportInfo(id='10329', slug='Barcelona', iata='BCN', persian_name='بارسلونا', english_name='Barcelona'),
    AirportInfo(id='10330', slug='Semnan', iata='SNX', persian_name='سمنان', english_name='Semnan'),
    AirportInfo(id='10331', slug='shandiz', iata='TTQ', persian_name='تست', english_name='shandiz'),
    AirportInfo(id='10332', slug='torghabe', iata='UGT', persian_name='تست', english_name='torghabe'),
    AirportInfo(id='10335', slug='Tashkent', iata='TAS', persian_name='تاشکند', english_name='Tashkent'),
    AirportInfo(id='10336', slug='Sohar', iata='OHS', persian_name='صحار(عمان)', english_name='Sohar'),
    AirportInfo(id='10337', slug='Jask', iata='JSK', persian_name='جاسک', english_name='Jask'),
    AirportInfo(id='10338', slug='Samsun', iata='SZF', persian_name='سامسون', english_name='Samsun'),
    AirportInfo(id='10339', slug='Bukhara', iata='BHK', persian_name='بخارا', english_name='Bukhara'),
    AirportInfo(id='10340', slug='Siri', iata='SXI', persian_name='سیری', english_name='Siri'),
    AirportInfo(id='10341', slug='Aghajari', iata='AKW', persian_name='امیدیه/آغاجری', english_name='Aghajari'),
    AirportInfo(id='10342', slug='Van', iata='VAN', persian_name='وان', english_name='Van'),
    AirportInfo(id='10343', slug='Cairo', iata='CAI', persian_name='قاهره', english_name='Cairo'),
    AirportInfo(id='10344', slug='Berlin', iata='BER', persian_name='برلین', english_name='Berlin'),
    AirportInfo(id='10345', slug='London Gatwick', iata='LGW', persian_name='گاتویک لندن', english_name='London Gatwick'),
    AirportInfo(id='10346', slug='Aleppo', iata='ALP', persian_name='حلب', english_name='Aleppo'),
    AirportInfo(id='10347', slug='Medina', iata='MED', persian_name='مدینه', english_name='Medina'),
    AirportInfo(id='10350', slug='Jeddah Mecca', iata='JED', persian_name='جده مکه', english_name='Jeddah Mecca'),
    AirportInfo(id='10374', slug='Dammam', iata='DMM', persian_name='دمام', english_name='Dammam'),
    AirportInfo(id='10351', slug='Dalaman', iata='DLM', persian_name='دالامان', english_name='Dalaman'),
    AirportInfo(id='10352', slug='Moscow_Sheremetyevo', iata='SVO', persian_name='مسکو', english_name='Moscow_Sheremetyevo'),
    AirportInfo(id='10365', slug='Phuket', iata='HKT', persian_name='پوکت', english_name='Phuket'),
    AirportInfo(id='10375', slug='Tunisia', iata='MIR', persian_name='تونس', english_name='Tunisia'),
    AirportInfo(id='10376', slug='quetta', iata='UET', persian_name='کویته', english_name='quetta'),
    AirportInfo(id='10377', slug='Volgograd', iata='VOG', persian_name='ولگوگراد', english_name='Volgograd'),
    AirportInfo(id='10378', slug='Minsk', iata='MSQ', persian_name='مینسک', english_name='Minsk'),
    AirportInfo(id='10379', slug='Hanoi', iata='HAN', persian_name='هانوی', english_name='Hanoi'),
    AirportInfo(id='10380', slug='Ho Chi Minh', iata='SGN', persian_name='هوشی مین', english_name='Ho Chi Minh'),
    AirportInfo(id='10000', slug='Tehran', iata='IKA', persian_name='امام خمینی', english_name='Imam Khomaini'),

]

# Lookup indexes
_BY_IATA: Dict[str, AirportInfo] = {}
_BY_ID: Dict[str, AirportInfo] = {}
_BY_SLUG: Dict[str, AirportInfo] = {}
_BY_PERSIAN: Dict[str, AirportInfo] = {}

for _ap in AIRPORTS:
    if _ap.iata and _ap.iata != 'همه':
        _BY_IATA[_ap.iata.upper()] = _ap
    _BY_ID[_ap.id] = _ap
    _BY_SLUG[_ap.slug.lower()] = _ap
    _BY_SLUG[_ap.english_name.lower()] = _ap
    _BY_PERSIAN[_ap.persian_name.strip()] = _ap

def find_airport(query: str) -> Optional[AirportInfo]:
    """
    Lookup an airport by IATA code, 5-digit ID, Persian name, or English name.
    """
    if not query:
        return None
    q = query.strip()
    q_upper = q.upper()
    q_lower = q.lower()
    
    # 1. By IATA code
    if q_upper in _BY_IATA:
        return _BY_IATA[q_upper]
        
    # 2. By 5-digit city ID
    if q in _BY_ID:
        return _BY_ID[q]
        
    # 3. By Persian name (exact match)
    if q in _BY_PERSIAN:
        return _BY_PERSIAN[q]
        
    # 4. By English name / slug
    if q_lower in _BY_SLUG:
        return _BY_SLUG[q_lower]
        
    # 5. Fuzzy match on Persian or English
    for ap in AIRPORTS:
        if q in ap.persian_name or ap.persian_name in q:
            return ap
        if q_lower in ap.english_name.lower() or ap.english_name.lower() in q_lower:
            return ap
            
    return None

def resolve_route(origin: str, destination: str) -> tuple[AirportInfo, AirportInfo]:
    """
    Resolves both origin and destination into AirportInfo objects.
    Raises ValueError if either cannot be resolved.
    """
    orig_ap = find_airport(origin)
    if not orig_ap:
        raise ValueError(f'Origin "{origin}" could not be resolved to a known Safarchin airport.')
        
    dest_ap = find_airport(destination)
    if not dest_ap:
        raise ValueError(f'Destination "{destination}" could not be resolved to a known Safarchin airport.')
        
    return orig_ap, dest_ap
