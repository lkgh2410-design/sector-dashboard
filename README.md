# 섹터 관심도 대시보드

## 파일 구조
```
sector_dashboard/
├── sectors.py        # 키워드 딕셔너리 (대/중/소 3단계)
├── collector.py      # 수집 + DB 저장 (구글 트렌드 + 네이버 뉴스)
├── app.py            # Streamlit 대시보드
├── requirements.txt  # 패키지 목록
└── sector_data.db    # 자동 생성됨
```

## 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 앱 실행
```bash
streamlit run app.py
```
→ 최초 실행 시 최근 7일치 데이터 자동 수집 (약 5~10분 소요)
→ 이후 매일 18:00 자동 수집

### 3. 수동 수집 (테스트용)
```bash
python collector.py
```

## 주의사항
- 구글 트렌드는 요청 간격이 짧으면 차단될 수 있음 → 자동으로 2초 간격 적용
- 네이버 뉴스 크롤링은 1초 간격 적용
- 전체 키워드 1회 수집에 약 5~10분 소요
- VPN 사용 시 구글 트렌드 수집 오류 발생 가능

## 기능 요약

| 탭 | 내용 |
|---|---|
| 📈 일별 트렌드 | 구글 트렌드 관심도 추이 + 같은 중분류 키워드 비교 |
| 📰 뉴스 & 감성 | 일별 기사 수 + 긍정/부정 감성 분포 |
| 🗺️ 섹터 전체 지도 | 대분류 전체 키워드 순위 테이블 + 트리맵 |

## 커스터마이징
- `sectors.py`에서 키워드 추가/삭제
- `collector.py`의 `POS_WORDS`, `NEG_WORDS`에서 감성 사전 편집
- 수집 시각 변경: `collector.py` → `start_scheduler()`의 `hour=18` 수정
