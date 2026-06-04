"""
daily_report.py
Daily 리포트 생성 + Claude API 해석 + 텔레그램 발송
"""

import os
import sys
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collectors.collect_daily import collect_all


# ─────────────────────────────────────────
# 환경변수
# ─────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ['TELEGRAM_TOKEN_MARKET']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_DAILY']
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# 한국투자증권 API (없으면 해당 지표 건너뜀)
KIS_APP_KEY      = os.environ.get('KIS_APP_KEY', '')
KIS_APP_SECRET   = os.environ.get('KIS_APP_SECRET', '')
KIS_ACCESS_TOKEN = os.environ.get('KIS_ACCESS_TOKEN', '')


# ─────────────────────────────────────────
# 이상 신호 1차 판단 (규칙 기반)
# ─────────────────────────────────────────
def detect_signals(d):
    """
    각 지표별 이상 신호 감지
    반환: [(지표명, 수치문자열, 경고내용), ...]
    """
    signals = []

    # VIX
    if d.get('VIX') and d['VIX'] > 25:
        signals.append(('VIX', f"{d['VIX']}", f"공포 구간 진입 (25 이상)"))
    if d.get('VIX_chg') and d['VIX_chg'] > 3:
        signals.append(('VIX 급등', f"+{d['VIX_chg']}", "하루 3포인트 이상 급등"))

    # VVIX
    if d.get('VVIX') and d['VVIX'] > 100:
        signals.append(('VVIX', f"{d['VVIX']}", "VIX 폭발 선행 경고 수준 (100 이상)"))

    # Put/Call Ratio
    if d.get('PC_ratio') and d['PC_ratio'] > 1.1:
        signals.append(('P/C Ratio', f"{d['PC_ratio']}", "옵션 시장 공포 심리 (1.1 이상)"))
    if d.get('PC_ratio') and d['PC_ratio'] < 0.5:
        signals.append(('P/C Ratio', f"{d['PC_ratio']}", "과도한 낙관론, 과열 가능성 (0.5 이하)"))

    # HYG/LQD
    if d.get('HYG_LQD_chg_pct') and d['HYG_LQD_chg_pct'] < -0.5:
        signals.append(('HYG/LQD', f"{d['HYG_LQD_chg_pct']}%", "신용 스프레드 확대 경고"))
    if d.get('HYG_LQD_5d_drop'):
        signals.append(('HYG/LQD', '5일 연속 하락', "정크본드 투매 신호, 신용 위험 증가"))

    # DXY
    if d.get('DXY_5d_chg') and d['DXY_5d_chg'] > 2.0:
        signals.append(('DXY', f"5일 +{d['DXY_5d_chg']}%", "달러 강세 경고, 신흥국 압박 가능성"))
    if d.get('DXY') and d['DXY'] > 105:
        signals.append(('DXY', f"{d['DXY']}", "달러 강세 구간 (105 이상)"))

    # 공포탐욕지수
    if d.get('FG_score') is not None:
        if d['FG_score'] <= 25:
            signals.append(('공포탐욕지수', f"{d['FG_score']} ({d['FG_rating']})", "극단적 공포 구간 (역발상 매수 신호 가능)"))
        elif d['FG_score'] >= 75:
            signals.append(('공포탐욕지수', f"{d['FG_score']} ({d['FG_rating']})", "극단적 탐욕 구간 (과열 경고)"))

    # 환율/KOSPI 괴리
    if d.get('KRW_1d_chg') and abs(d['KRW_1d_chg']) > 0.8:
        direction = "급등 (원화 약세)" if d['KRW_1d_chg'] > 0 else "급락 (원화 강세)"
        signals.append(('원/달러 환율', f"{d['KRW']}원 ({d['KRW_1d_chg']:+}%)", f"환율 {direction}, 하루 0.8% 이상 변동"))
    if d.get('KRW_KOSPI_divergence'):
        signals.append(('환율/KOSPI 괴리', f"환율↑ KOSPI 버팀", "외국인 조용히 이탈 중 가능성"))

    return signals


# ─────────────────────────────────────────
# Claude API 해석 요청
# ─────────────────────────────────────────
def get_claude_interpretation(d, signals):
    """
    이상 신호가 있을 때만 Claude API 호출
    이상 신호 없으면 None 반환 (한 줄 종합 판단은 규칙 기반으로 처리)
    """
    if not signals:
        return None
    if not ANTHROPIC_API_KEY:
        return None

    signal_text = "\n".join([f"- {s[0]}: {s[1]} → {s[2]}" for s in signals])

    # 수치 요약
    metrics_text = f"""
VIX: {d.get('VIX')} (전일 대비 {d.get('VIX_chg'):+})" if d.get('VIX_chg') else f"VIX: {d.get('VIX')}
VVIX: {d.get('VVIX')}
Put/Call Ratio: {d.get('PC_ratio')}
HYG/LQD 비율: {d.get('HYG_LQD_ratio')} ({d.get('HYG_LQD_chg_pct'):+.2f}%" if d.get('HYG_LQD_chg_pct') else "")
DXY: {d.get('DXY')} (5일 변화: {d.get('DXY_5d_chg'):+.1f}%" if d.get('DXY_5d_chg') else "")
공포탐욕지수: {d.get('FG_score')} ({d.get('FG_rating')})
원/달러: {d.get('KRW')}원 (일간 {d.get('KRW_1d_chg'):+.2f}%" if d.get('KRW_1d_chg') else "")
KOSPI: {d.get('KOSPI')} ({d.get('KOSPI_1d_chg'):+.2f}%" if d.get('KOSPI_1d_chg') else "")
"""

    prompt = f"""당신은 시장 분석 전문가입니다. 오늘의 시장 지표 수치와 감지된 이상 신호를 바탕으로 간결하게 해석해주세요.

[오늘 수치]
{metrics_text}

[감지된 이상 신호]
{signal_text}

[요청사항]
1. 각 이상 신호를 1~2문장으로 간단히 해석해주세요. 전문 용어는 괄호 안에 설명을 추가해주세요.
2. 신호들을 종합한 판단을 딱 한 줄로 작성해주세요. ("종합 판단: ..." 형식)
3. 전체 응답은 10줄을 넘지 않게 해주세요.
4. 한국어로 작성해주세요."""

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
        return result['content'][0]['text'].strip()
    except Exception as e:
        print(f"[오류] Claude API: {e}")
        return None


# ─────────────────────────────────────────
# 메시지 조립
# ─────────────────────────────────────────
def build_message(d, signals, interpretation):
    today = d.get('collected_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    lines = []

    lines.append(f"📊 Daily Market Report")
    lines.append(f"🗓 {today}")
    lines.append("─" * 30)

    # 수치 요약
    def fmt(val, suffix='', plus=False):
        if val is None:
            return 'N/A'
        if plus and isinstance(val, (int, float)):
            return f"{val:+.2f}{suffix}"
        return f"{val}{suffix}"

    lines.append("【변동성】")
    lines.append(f"  VIX    {fmt(d.get('VIX'))}  ({fmt(d.get('VIX_chg'), plus=True)})")
    lines.append(f"  VVIX   {fmt(d.get('VVIX'))}  ({fmt(d.get('VVIX_chg'), plus=True)})")
    lines.append(f"  P/C    {fmt(d.get('PC_ratio'))}")

    lines.append("【유동성】")
    lines.append(f"  HYG/LQD  {fmt(d.get('HYG_LQD_ratio'))}  ({fmt(d.get('HYG_LQD_chg_pct'), '%', plus=True)})")
    lines.append(f"  DXY      {fmt(d.get('DXY'))}  (5일 {fmt(d.get('DXY_5d_chg'), '%', plus=True)})")

    lines.append("【심리】")
    fg_str = f"{fmt(d.get('FG_score'))} / {d.get('FG_rating', 'N/A')}"
    lines.append(f"  공포탐욕  {fg_str}")

    lines.append("【한국 시장】")
    lines.append(f"  KOSPI    {fmt(d.get('KOSPI'))}  ({fmt(d.get('KOSPI_1d_chg'), '%', plus=True)})")
    lines.append(f"  원/달러  {fmt(d.get('KRW'))}원  ({fmt(d.get('KRW_1d_chg'), '%', plus=True)})")

    # 삼성전자
    sam = d.get('samsung_foreign')
    if sam:
        try:
            sam_price = f"{int(str(sam['price']).replace(',', '')):,}"
        except Exception:
            sam_price = sam['price']
        lines.append(f"  삼성전자  {sam_price}원  외국인 {sam['foreign_net_buy']}주  보유율 {sam['foreign_rate']}%")

    hyn = d.get('hynix_foreign')
    if hyn:
        try:
            hyn_price = f"{int(str(hyn['price']).replace(',', '')):,}"
        except Exception:
            hyn_price = hyn['price']
        lines.append(f"  SK하이닉스  {hyn_price}원  외국인 {hyn['foreign_net_buy']}주  보유율 {hyn['foreign_rate']}%")

    # 시장 투자자 동향
    trend = d.get('market_investor_trend')
    if trend:
        lines.append("【코스피 투자자 동향】")
        def fmt_bil(v):
            try:
                n = int(str(v).replace(',',''))
                return f"{n:+,}억"
            except:
                return str(v)
        lines.append(f"  외국인  {fmt_bil(trend.get('foreign_net','N/A'))}")
        lines.append(f"  기관    {fmt_bil(trend.get('inst_net','N/A'))}")
        lines.append(f"  개인    {fmt_bil(trend.get('indiv_net','N/A'))}")

    # 외국인 TOP5
    if d.get('foreign_buy_top5'):
        lines.append("【외국인 순매수 TOP5】")
        for i, item in enumerate(d['foreign_buy_top5'], 1):
            lines.append(f"  {i}. {item['name']}  {item['amount']}")

    lines.append("─" * 30)

    # 이상 신호 or 정상
    if signals:
        lines.append("⚠️ 감지된 신호")
        for s in signals:
            lines.append(f"  • {s[0]}: {s[1]}")
            lines.append(f"    → {s[2]}")

        if interpretation:
            lines.append("")
            lines.append("🤖 AI 해석")
            lines.append(interpretation)
        else:
            # Claude API 없을 때 신호 개수로 단순 판단
            count = len(signals)
            if count >= 4:
                verdict = "⚠️ 종합 판단: 복수 경고 신호 동시 발생, 리스크 관리 필요"
            elif count >= 2:
                verdict = "⚠️ 종합 판단: 일부 지표 이상 신호, 주의 요망"
            else:
                verdict = "⚠️ 종합 판단: 단일 신호 감지, 모니터링 강화"
            lines.append("")
            lines.append(verdict)
    else:
        lines.append("✅ 종합 판단: 전반적 안정, 특이 신호 없음")

    return "\n".join(lines)


# ─────────────────────────────────────────
# 텔레그램 발송
# ─────────────────────────────────────────
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # 텔레그램 메시지 최대 4096자 제한 처리
    if len(text) > 4000:
        text = text[:3997] + "..."
    resp = requests.post(url, data={
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text
    })
    if resp.status_code != 200:
        print(f"[오류] 텔레그램 발송 실패: {resp.text}")
    else:
        print("[완료] 텔레그램 발송 성공")


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────
def main():
    # 1. 데이터 수집
    data = collect_all(
        app_key=KIS_APP_KEY or None,
        app_secret=KIS_APP_SECRET or None,
        access_token=KIS_ACCESS_TOKEN or None
    )

    # 2. 이상 신호 감지
    signals = detect_signals(data)
    print(f"[신호] {len(signals)}개 감지됨")

    # 3. Claude API 해석 (이상 신호 있을 때만)
    interpretation = get_claude_interpretation(data, signals)

    # 4. 메시지 조립
    message = build_message(data, signals, interpretation)
    print(message)

    # 5. 텔레그램 발송
    send_telegram(message)


if __name__ == '__main__':
    main()
