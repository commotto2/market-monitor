# Market Monitor

VIX 모니터링을 확장한 종합 시장 모니터링 시스템.
텔레그램 봇(@market_monitor_ssh_bot)으로 일간/주간/격주/월간 리포트 자동 발송.

---

## 파일 구조

```
market-monitor/
├── .github/workflows/
│   ├── daily_report.yml       # 평일 16:30 KST
│   └── weekend_report.yml     # 토요일 08:30 KST (주간 + 격주 + 월간 통합)
├── collectors/
│   ├── collect_daily.py       # 일간 지표 10개 수집
│   ├── collect_weekly.py      # 주간 지표 8개 수집
│   ├── collect_biweekly.py    # 격주 지표 3개 수집
│   └── collect_monthly.py     # 월간 지표 3개 수집
├── reports/
│   ├── daily_report.py        # 일간 리포트 생성/발송
│   ├── weekly_report.py       # 주간 리포트 생성/발송
│   ├── biweekly_report.py     # 격주 리포트 생성/발송
│   └── monthly_report.py      # 월간 리포트 생성/발송
└── README.md
```

---

## 수신 스케줄

| 리포트 | 발송 시각 (KST) | 채팅방 |
|---|---|---|
| Daily | 평일 17:00~17:30 | 📊 Market Daily |
| Weekly | 토요일 09:00~10:00 | 📅 Market Weekly |
| Biweekly | 격주 토요일 (홀수 주) | 📆 Market Biweekly |
| Monthly | 매월 첫째 토요일 | 🗓 Market Monthly |

---

## GitHub Secrets 목록

### 필수 (반드시 설정)
| Secret 이름 | 내용 |
|---|---|
| `TELEGRAM_TOKEN_MARKET` | @market_monitor_ssh_bot 토큰 |
| `TELEGRAM_CHAT_DAILY` | Daily 방 Chat ID |
| `TELEGRAM_CHAT_WEEKLY` | Weekly 방 Chat ID |
| `TELEGRAM_CHAT_BIWEEKLY` | Biweekly 방 Chat ID |
| `TELEGRAM_CHAT_MONTHLY` | Monthly 방 Chat ID |

### 권장 (없으면 일부 기능 비활성화)
| Secret 이름 | 내용 | 없을 때 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API 키 | AI 해석 없이 수치만 발송 |
| `FRED_API_KEY` | FRED API 키 (무료) | TED 스프레드, MOVE 백업 비활성화 |

### 선택 (한국 수급 데이터용)
| Secret 이름 | 내용 | 없을 때 |
|---|---|---|
| `KIS_APP_KEY` | 한국투자증권 앱키 | 외국인/기관 수급 건너뜀 |
| `KIS_APP_SECRET` | 한국투자증권 앱시크릿 | 동일 |
| `KIS_ACCESS_TOKEN` | 한국투자증권 접근토큰 | 동일 |

---

## API 발급 방법

### FRED API (무료, 5분)
1. https://fred.stlouisfed.org 가입
2. My Account → API Keys → Request API Key

### 한국투자증권 Open API (무료)
1. https://apiportal.koreainvestment.com 접속
2. 계좌 연동 후 앱키/앱시크릿 발급
3. Access Token은 매일 갱신 필요
   → GitHub Actions에서 자동 갱신하려면 별도 스크립트 필요

---

## 지표 목록

### Daily (10개) — 평일 매일
1. VIX vs VVIX
2. Put/Call Ratio
3. HYG/LQD 스프레드
4. DXY 모멘텀
5. 공포탐욕지수 (CNN)
6. 외국인 코스피 순매수 TOP5
7. 기관 코스피 순매수 TOP5
8. 삼성전자 외국인 수급
9. SK하이닉스 외국인 수급
10. 원/달러 환율 + KOSPI 괴리

### Weekly (8개) — 매주 토요일
11. 장단기 금리차 (10년-2년)
12. MOVE 인덱스
13. TED 스프레드
14. 섹터 ETF 순위 (11개, 차트 포함)
15. QQQ/SPY 비율
16. IVW/IVE 비율
17. IWM/SPY 비율
18. 코스피 신용잔고

### Biweekly (3개) — 격주 토요일
19. S&P500 200일선 위 종목 비율
20. McClellan Oscillator
21. 외국인 코스피 지분율 추이

### Monthly (3개) — 매월 첫째 토요일
22. 삼성전자/SK하이닉스 외국인 지분율 월간
23. KOSPI vs S&P500 상대 수익률
24. 원/달러 환율 월간 변동폭

---

## 수동 실행 방법

GitHub → Actions → 해당 workflow → Run workflow
- `force_biweekly`: true 입력 시 격주 리포트 강제 실행
- `force_monthly`: true 입력 시 월간 리포트 강제 실행
