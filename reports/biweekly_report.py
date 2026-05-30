"""
biweekly_report.py
격주 리포트 생성 + 텔레그램 발송
"""

import os
import sys
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collectors.collect_biweekly import collect_all_biweekly

TELEGRAM_TOKEN   = os.environ['TELEGRAM_TOKEN_MARKET']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_BIWEEKLY']
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')


def detect_signals_biweekly(d):
    signals = []

    # 200일선 비율
    ratio = d.get('above_ma200_ratio')
    if ratio is not None:
        if ratio < 30:
            signals.append(('200일선 위 비율', f"{ratio}%", "광범위한 하락세, 시장 체력 저하"))
        elif ratio < 50:
            signals.append(('200일선 위 비율', f"{ratio}%", "과반 종목이 장기 추세 이탈 중"))

    # McClellan
    mc = d.get('mcclellan')
    if mc is not None:
        if mc < -100:
            signals.append(('McClellan', f"{mc}", "강한 하락 에너지, 과매도 (역발상 반등 가능)"))
        elif mc > 100:
            signals.append(('McClellan', f"{mc}", "강한 상승 에너지, 과매수 주의"))

    if d.get('mcclellan_zero_cross'):
        signals.append(('McClellan 교차', d['mcclellan_zero_cross'], "추세 전환 신호"))

    # 외국인 지분율
    chg = d.get('foreign_ownership_2m_chg')
    if chg is not None and chg < -1.0:
        signals.append(('외국인 지분율', f"2개월 {chg:+.2f}%p", "구조적 외국인 이탈 진행 중"))

    return signals


def get_claude_interpretation_biweekly(d, signals):
    if not signals or not ANTHROPIC_API_KEY:
        return None

    signal_text = "\n".join([f"- {s[0]}: {s[1]} → {s[2]}" for s in signals])

    prompt = f"""시장 분석 전문가로서 격주 시장 내부 강도 지표를 해석해주세요.

[수치]
S&P500 200일선 위 종목 비율: {d.get('above_ma200_ratio')}% ({d.get('above_ma200_count')}/{d.get('above_ma200_total')}종목)
McClellan Oscillator: {d.get('mcclellan')}
외국인 코스피 지분율: {d.get('foreign_ownership_rate')}% (2개월 변화: {d.get('foreign_ownership_2m_chg'):+.2f}%p" if d.get('foreign_ownership_2m_chg') else ")")

[감지된 신호]
{signal_text}

[요청]
1. 시장 내부 체력 상태를 2문장으로 평가해주세요.
2. 이상 신호가 있으면 1문장씩 해석해주세요.
3. "종합 판단: ..." 한 줄로 마무리해주세요.
4. 전체 8줄 이내, 한국어로 작성해주세요."""

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
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        return resp.json()['content'][0]['text'].strip()
    except Exception as e:
        print(f"[오류] Claude API (biweekly): {e}")
        return None


def build_message_biweekly(d, signals, interpretation):
    today = d.get('collected_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    lines = []

    lines.append("📆 Biweekly Market Report")
    lines.append(f"🗓 {today}")
    lines.append("─" * 30)

    lines.append("【시장 내부 강도】")
    ratio = d.get('above_ma200_ratio')
    if ratio is not None:
        bar = "█" * int(ratio // 10) + "░" * (10 - int(ratio // 10))
        lines.append(f"  200일선 위 비율  {ratio}%")
        lines.append(f"  [{bar}]")

        if ratio >= 70:
            lines.append("  → 건강한 강세장")
        elif ratio >= 50:
            lines.append("  → 보통, 선별적 강세")
        elif ratio >= 30:
            lines.append("  → ⚠ 약세 전환 경고")
        else:
            lines.append("  → ⚠⚠ 광범위한 하락")
    else:
        lines.append("  200일선 위 비율  N/A")

    mc = d.get('mcclellan')
    if mc is not None:
        cross_str = f"  ★ {d['mcclellan_zero_cross']}" if d.get('mcclellan_zero_cross') else ""
        lines.append(f"  McClellan  {mc}{cross_str}")
    else:
        lines.append("  McClellan  N/A")

    lines.append("【외국인 코스피 지분율】")
    rate = d.get('foreign_ownership_rate')
    chg  = d.get('foreign_ownership_2m_chg')
    if rate is not None:
        chg_str = f"  (2개월 {chg:+.2f}%p)" if chg is not None else ""
        lines.append(f"  현재 {rate}%{chg_str}")
        lines.append(f"  기준일: {d.get('foreign_ownership_date', '')}")
    else:
        lines.append("  N/A")

    lines.append("─" * 30)

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
            lines.append("\n⚠️ 종합 판단: 시장 내부 이상 신호 감지, 모니터링 강화")
    else:
        lines.append("✅ 종합 판단: 시장 내부 체력 양호, 특이 신호 없음")

    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:3997] + "..."
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    print("[완료] 격주 리포트 발송")


def main():
    data = collect_all_biweekly()
    signals = detect_signals_biweekly(data)
    interpretation = get_claude_interpretation_biweekly(data, signals)
    message = build_message_biweekly(data, signals, interpretation)
    print(message)
    send_telegram(message)


if __name__ == '__main__':
    main()
