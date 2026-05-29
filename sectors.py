# sectors.py
# 대분류 > 중분류 > 소분류(키워드) 3단계 구조
# 각 키워드가 구글 트렌드 + 네이버 뉴스 수집 단위

SECTORS = {
    "반도체": {
        "메모리": [
            "HBM", "HBM3E", "HBM4", "DRAM", "DDR5", "LPDDR5",
            "낸드플래시", "NAND", "SSD", "HDD"
        ],
        "파운드리/패키징": [
            "파운드리", "CoWoS", "HBM 패키징", "FCBGA",
            "유리기판", "ABF기판", "2nm 공정", "3nm 공정"
        ],
        "소재/장비": [
            "포토레지스트", "EUV 장비", "식각장비", "증착장비",
            "실리콘 웨이퍼", "CMP슬러리", "희토류"
        ],
        "시스템반도체": [
            "AP 반도체", "SoC", "PMIC", "CIS 이미지센서",
            "DDI", "RF칩", "FPGA"
        ],
    },
    "AI/데이터센터": {
        "AI칩/가속기": [
            "GPU", "H100", "B200 GPU", "NPU", "AI가속기",
            "엣지AI", "ASIC", "TPU"
        ],
        "서버/네트워크": [
            "AI서버", "GPU서버", "이더넷스위치", "InfiniBand",
            "광트랜시버", "광케이블", "400G"
        ],
        "DC인프라": [
            "데이터센터", "하이퍼스케일", "액침냉각", "수냉각",
            "IDC", "UPS 전원"
        ],
        "수동부품": [
            "MLCC", "인덕터", "커넥터", "PCB", "FC-BGA"
        ],
    },
    "전력/에너지": {
        "송배전/전력망": [
            "변압기", "초고압변압기", "HVDC", "전력케이블",
            "GIS 차단기", "스마트그리드"
        ],
        "전력반도체": [
            "IGBT", "SiC 반도체", "GaN 반도체",
            "전력반도체", "인버터", "컨버터"
        ],
        "신재생에너지": [
            "태양광", "태양전지", "페로브스카이트",
            "해상풍력", "풍력발전", "수소에너지", "연료전지"
        ],
        "에너지저장": [
            "ESS", "전고체배터리", "LFP배터리",
            "대용량ESS", "바나듐배터리"
        ],
    },
    "원전": {
        "건설/설비": [
            "원전건설", "APR1400", "SMR", "소형모듈원전",
            "원자로", "터빈발전기", "원전배관", "원전밸브"
        ],
        "핵연료/소재": [
            "우라늄", "농축우라늄", "핵연료봉",
            "지르코늄", "피복관"
        ],
        "안전/계측": [
            "원전계측제어", "원전안전계통", "방사선차폐",
            "원전유지보수", "사용후핵연료"
        ],
        "수출/확장": [
            "원전수출", "체코원전", "UAE원전",
            "원전재가동", "원전확대"
        ],
    },
}

# 유틸: 전체 키워드 리스트
def get_all_keywords():
    result = []
    for big, mids in SECTORS.items():
        for mid, keywords in mids.items():
            for kw in keywords:
                result.append({"대분류": big, "중분류": mid, "키워드": kw})
    return result

# 유틸: 대분류 리스트
def get_big_sectors():
    return list(SECTORS.keys())

# 유틸: 특정 대분류의 중분류 리스트
def get_mid_sectors(big):
    return list(SECTORS.get(big, {}).keys())

# 유틸: 특정 중분류의 키워드 리스트
def get_keywords(big, mid):
    return SECTORS.get(big, {}).get(mid, [])
