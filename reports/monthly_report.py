"""
monthly_report.py
월간 리포트 생성 + 텔레그램 발송
매월 첫째 주 토요일
"""

import os
import sys
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collectors.collect_monthly import collect_all_monthly

TELEGRAM_TOKEN   = os.environ['TELEGRAM_TOKEN_MARKET']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_MONTHLY']
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
KIS_APP_KEY      = os.environ.get('KIS_APP_KEY', '')
KIS_APP_SECRET   = os.environ.get('KIS_APP_SECRET', '')
KIS_ACCESS_TOKEN = os.environ.get('KIS_ACCESS_TOKEN', '')


def detect_signals_monthly(d):
    signals = []

    # 상대 수익률
    rel_1m = d.get('rel_ret_1m')
    rel_3m = d.get('rel_ret_3m')
    if rel_1m is not None and rel_1m < -5:
        signals.append(('KOSPI/S&P500', f"1개월 격차 {rel_1m:+.2f}%", "코스피 심각한 상대 약세"))
    if rel_3m is not None and rel_3m < -10:
        signals.append(('KOSPI/S&P500', f"3개월 격차 {rel_3m:+.2f}%", "코스피 구조적 디스카운트 확대"))

    # 환율 변동폭
    range_val = d.get('krw_last_month_range')
    if range_val and range_val > 50:
        signals.append(('환율 변동폭', f"월간 레인지 {range_val}원", "환율 불안정 심화"))

    return signals


def get_claude_interpretation_monthly(d, signals):
    if not ANTHROPIC_API_KEY:
        return None

    signal_text = "\n".join([f"- {s[0]}: {s[1]} → {s[2]}" for s in signals]) if signals else "없음"

    stocks = d.get('monthly_stocks', {})
    sam = stocks.get('samsung', {}) or {}
    hyn = stocks.get('hynix', {}) or {}

    sam_price    = sam.get('price', 'N/A')
    sam_frate    = sam.get('foreign_rate', 'N/A')
    hyn_price    = hyn.get('price', 'N/A')
    hyn_frate    = hyn.get('foreign_rate', 'N/A')
    sp500_1m     = d.get('sp500_ret_1m', 'N/A')
    sp500_3m     = d.get('sp500_ret_3m', 'N/A')
    sp500_1y     = d.get('sp500_ret_1y', 'N/A')
    krw_cur      = d.get('krw_current', 'N/A')
    krw_lo       = d.get('krw_last_month_low', 'N/A')
    krw_hi       = d.get('krw_last_month_high', 'N/A')

    prompt = (
        "시장 분석 전문가로서 이번 달 한국 시장 구조적 흐름을 평가해주세요.\n\n"
        "[수치]\n"
        f"삼성전자: {sam_price}원  외국인 보유율 {sam_frate}\n"
        f"SK하이닉스: {hyn_price}원  외국인 보유율 {hyn_frate}\n\n"
        f"S&P500 수익률: 1개월 {sp500_1m}  3개월 {sp500_3m}  1년 {sp500_1y}\n"
        f"환율: {krw_cur}원  (지난달 레인지: {krw_lo}~{krw_hi}원)\n\n"
        f"[감지된 신호]\n{signal_text}\n\n"
        "[요청]\n"
        "1. 이번 달 한국 시장의 구조적 특징을 2문장으로 요약해주세요.\n"
        "2. 삼성전자/SK하이닉스 주가 흐름을 1문장으로 평가해주세요.\n"
        "3. 환율 동향을 1문장으로 해석해주세요.\n"
        "4. \"종합 판단: ...\" 한 줄로 마무리해주세요.\n"
        "5. 전체 8줄 이내, 한국어로 작성해주세요."
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        result = resp.json()
        if 'content' not in result:
            print(f"[오류] Claude API 응답 구조 이상: {result}")
            return None
        return result['content'][0]['text'].strip()
    except Exception as e:
        print(f"[오류] Claude API (monthly): {e}")
        return None


def build_message_monthly(d, signals, interpretation):
    today = d.get('collected_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    month_str = datetime.now().strftime('%Y년 %m월')
    lines = []

    lines.append(f"🗓 Monthly Market Report")
    lines.append(f"📅 {month_str}  ({today})")
    lines.append("─" * 30)

    # 종목별 수급
    stocks = d.get('monthly_stocks', {})
    lines.append("【핵심 종목 외국인 수급】")
    for key, label in [('samsung', '삼성전자'), ('hynix', 'SK하이닉스')]:
        s = stocks.get(key)
        if s:
            price_str = f"{s['price']:,}원" if isinstance(s.get('price'), (int, float)) else f"{s.get('price', 'N/A')}원"
            lines.append(f"  {label}")
            lines.append(f"    주가: {price_str}  외국인 보유율: {s.get('foreign_rate', 'N/A')}%")
        else:
            lines.append(f"  {label}: N/A")

    # 상대 수익률
    lines.append("【KOSPI vs S&P500】")
    lines.append(f"  {'기간':6}  {'KOSPI':>8}  {'S&P500':>8}  {'격차':>8}")
    lines.append(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}")
    for period, k_key, s_key, r_key in [
        ('1개월', 'kospi_ret_1m', 'sp500_ret_1m', 'rel_ret_1m'),
        ('3개월', 'kospi_ret_3m', 'sp500_ret_3m', 'rel_ret_3m'),
        ('1년',   'kospi_ret_1y', 'sp500_ret_1y', 'rel_ret_1y')
    ]:
        k = d.get(k_key)
        s = d.get(s_key)
        r = d.get(r_key)
        k_str = f"{k:+.1f}%" if k is not None else "N/A"
        s_str = f"{s:+.1f}%" if s is not None else "N/A"
        r_str = f"{r:+.1f}%" if r is not None else "N/A"
        lines.append(f"  {period:6}  {k_str:>8}  {s_str:>8}  {r_str:>8}")

    # 환율 월간 변동
    lines.append("【환율 월간】")
    lines.append(f"  현재:    {d.get('krw_current', 'N/A')}원")
    if d.get('krw_last_month_low') and d.get('krw_last_month_high'):
        lines.append(f"  지난달:  {d['krw_last_month_low']}~{d['krw_last_month_high']}원  (레인지 {d.get('krw_last_month_range', 'N/A')}원)")
    if d.get('krw_3m_low') and d.get('krw_3m_high'):
        lines.append(f"  3개월:   {d['krw_3m_low']}~{d['krw_3m_high']}원")

    lines.append("─" * 30)

    # 이상 신호 / 종합 판단
    if signals:
        lines.append("⚠️ 감지된 신호")
        for s in signals:
            lines.append(f"  • {s[0]}: {s[1]}")
            lines.append(f"    → {s[2]}")

    if interpretation:
        lines.append("")
        lines.append("🤖 AI 월간 평가")
        lines.append(interpretation)
    else:
        if signals:
            lines.append("\n⚠️ 종합 판단: 구조적 이상 신호 감지, 포지션 점검 권장")
        else:
            lines.append("\n✅ 종합 판단: 월간 구조적 흐름 안정, 특이 신호 없음")

    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:3997] + "..."
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    print("[완료] 월간 리포트 발송")


def main():
    data = collect_all_monthly(
        app_key=KIS_APP_KEY or None,
        app_secret=KIS_APP_SECRET or None,
        access_token=KIS_ACCESS_TOKEN or None
    )
    signals = detect_signals_monthly(data)
    interpretation = get_claude_interpretation_monthly(data, signals)
    message = build_message_monthly(data, signals, interpretation)
    print(message)
    send_telegram(message)


if __name__ == '__main__':
    main()
