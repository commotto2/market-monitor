"""
weekly_report.py
Weekly 리포트 생성 + Claude API 해석 + 텔레그램 발송
매주 토요일 08:30 KST 수신 목표
"""

import os
import sys
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime
import io
import subprocess

# ─────────────────────────────────────────
# 한글 폰트 설정 (GitHub Actions Ubuntu 환경)
# ─────────────────────────────────────────
def setup_korean_font():
    try:
        # pip으로 한글 폰트 설치
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "koreanize-matplotlib", "-q"],
            capture_output=True, timeout=60
        )
        import koreanize_matplotlib  # noqa: F401
        print("[폰트] koreanize-matplotlib 적용")
    except Exception:
        # fallback: matplotlib 기본 한글 경고 무시
        import warnings
        warnings.filterwarnings("ignore", message="Glyph.*missing")
        print("[폰트] 한글 폰트 없음 → 경고 무시 처리")

setup_korean_font()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collectors.collect_weekly import collect_all_weekly


TELEGRAM_TOKEN   = os.environ['TELEGRAM_TOKEN_MARKET']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_WEEKLY']
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')


# ─────────────────────────────────────────
# 이상 신호 감지
# ─────────────────────────────────────────
def detect_signals_weekly(d):
    signals = []

    # 장단기 금리차
    if d.get('yield_inverted'):
        signals.append(('장단기 금리차', f"{d['yield_spread']:.3f}%", "수익률 곡선 역전 중 (경기침체 선행 신호)"))
    if d.get('yield_inversion_resolving'):
        signals.append(('장단기 금리차', f"{d['yield_spread']:.3f}%", "역전 해소 구간 — 오히려 침체 현실화 시점일 수 있음"))

    # MOVE
    if d.get('MOVE') and d['MOVE'] > 100:
        signals.append(('MOVE 인덱스', f"{d['MOVE']}", "채권 변동성 경고 수준 (100 이상)"))

    # TED 스프레드
    if d.get('TED_spread') and d['TED_spread'] > 0.5:
        signals.append(('TED 스프레드', f"{d['TED_spread']:.3f}%", "은행 간 신뢰 붕괴 경고 (0.5% 이상)"))

    # 섹터
    risk_mode = d.get('sector_risk_mode', '')
    if '리스크오프' in (risk_mode or ''):
        ranking = d.get('sector_ranking', [])
        top1 = ranking[0]['name'] if ranking else ''
        signals.append(('섹터 로테이션', f"1위: {top1}", f"{risk_mode}"))

    # 비율 지표
    for key, label, warn in [
        ('QQQ_SPY', 'QQQ/SPY', '나스닥 약세 지속, 기술주 이탈 신호'),
        ('IVW_IVE', 'IVW/IVE', '가치주 우위 지속, 리스크오프 구도'),
        ('IWM_SPY', 'IWM/SPY', '소형주 약세 지속, 경기 비관론 확산')
    ]:
        ratio_data = d.get(key)
        if ratio_data and not ratio_data.get('above_ma20') and ratio_data.get('chg_1m') and ratio_data['chg_1m'] < -2:
            signals.append((label, f"20일선 아래 / 월간 {ratio_data['chg_1m']:+.1f}%", warn))

    # 신용잔고 (코스피 시총 대비 비율은 별도 계산 필요, 여기서는 절대값 경고)
    if d.get('credit_balance_bil') and d['credit_balance_bil'] > 20000:
        signals.append(('코스피 신용잔고', f"{d['credit_balance_bil']:,.0f}억", "신용잔고 과다, 반대매매 위험"))

    return signals


# ─────────────────────────────────────────
# 섹터 ETF 차트 생성
# ─────────────────────────────────────────
def build_sector_chart(sector_ranking):
    if not sector_ranking:
        return None

    try:
        names   = [f"{r['ticker']}\n{r['name']}" for r in sector_ranking]
        returns = [r['ret_1w'] if r['ret_1w'] is not None else 0 for r in sector_ranking]
        tickers = [r['ticker'] for r in sector_ranking]

        # 색상: 방어=파랑, 공격=주황, 중립=회색
        defensive = {'XLU', 'XLP', 'XLV'}
        offensive = {'XLK', 'XLY', 'XLF'}
        colors = []
        for t in tickers:
            if t in defensive:
                colors.append('#4A90D9')
            elif t in offensive:
                colors.append('#E8702A')
            else:
                colors.append('#888888')

        fig, ax = plt.subplots(figsize=(12, 5))
        bars = ax.barh(names[::-1], returns[::-1], color=colors[::-1], edgecolor='white', height=0.6)

        # 수치 레이블
        for bar, val in zip(bars, returns[::-1]):
            ax.text(
                bar.get_width() + (0.05 if val >= 0 else -0.05),
                bar.get_y() + bar.get_height() / 2,
                f'{val:+.2f}%',
                va='center', ha='left' if val >= 0 else 'right',
                fontsize=9, color='black'
            )

        ax.axvline(0, color='black', linewidth=0.8, linestyle='-')
        ax.set_xlabel('1주 수익률 (%)', fontsize=10)
        ax.set_title(f'Sector ETF Weekly Performance\n{datetime.now().strftime("%Y-%m-%d")}',
                     fontsize=12, fontweight='bold')

        # 범례
        patches = [
            mpatches.Patch(color='#E8702A', label='공격 섹터 (XLK/XLY/XLF)'),
            mpatches.Patch(color='#4A90D9', label='방어 섹터 (XLU/XLP/XLV)'),
            mpatches.Patch(color='#888888', label='중립 섹터')
        ]
        ax.legend(handles=patches, loc='lower right', fontsize=8)
        ax.grid(axis='x', linestyle=':', alpha=0.5)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        return buf
    except Exception as e:
        print(f"[오류] 섹터 차트: {e}")
        return None


# ─────────────────────────────────────────
# Claude API 해석
# ─────────────────────────────────────────
def get_claude_interpretation_weekly(d, signals):
    if not signals or not ANTHROPIC_API_KEY:
        return None

    signal_text = "\n".join([f"- {s[0]}: {s[1]} → {s[2]}" for s in signals])
    ranking_text = ""
    if d.get('sector_ranking'):
        ranking_text = "\n".join([
            f"{i+1}위 {r['ticker']}({r['name']}) 1주 {r['ret_1w']:+.2f}%"
            for i, r in enumerate(d['sector_ranking'][:5])
        ])

    prompt = f"""시장 분석 전문가로서 이번 주 시장 지표를 해석해주세요.

[주요 수치]
장단기 금리차: {d.get('yield_spread')}% (10년-2년)
MOVE 인덱스: {d.get('MOVE')}
TED 스프레드: {d.get('TED_spread')}%
섹터 TOP5:
{ranking_text}
QQQ/SPY: {d.get('QQQ_SPY', {}).get('ratio')} (1주 {d.get('QQQ_SPY', {}).get('chg_1w'):+.2f}%" if d.get('QQQ_SPY') else "")
IWM/SPY: {d.get('IWM_SPY', {}).get('ratio')} (1주 {d.get('IWM_SPY', {}).get('chg_1w'):+.2f}%" if d.get('IWM_SPY') else "")

[감지된 이상 신호]
{signal_text if signal_text else "없음"}

[요청사항]
1. 이번 주 시장의 핵심 흐름을 2~3문장으로 요약해주세요.
2. 이상 신호가 있으면 각각 1문장으로 해석해주세요.
3. 다음 주 주의해야 할 점을 1문장으로 작성해주세요.
4. 마지막에 "종합 판단: ..." 형식으로 한 줄 요약해주세요.
5. 전체 10줄 이내, 한국어로 작성해주세요."""

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
        return resp.json()['content'][0]['text'].strip()
    except Exception as e:
        print(f"[오류] Claude API (weekly): {e}")
        return None


# ─────────────────────────────────────────
# 메시지 조립
# ─────────────────────────────────────────
def build_message_weekly(d, signals, interpretation):
    today = d.get('collected_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    lines = []

    lines.append(f"📅 Weekly Market Report")
    lines.append(f"🗓 {today}")
    lines.append("─" * 30)

    # 금리
    inv_str = " ⚠역전중" if d.get('yield_inverted') else ""
    lines.append("【금리】")
    lines.append(f"  10년물  {d.get('T10Y', 'N/A')}%")
    lines.append(f"  2년물   {d.get('T2Y', 'N/A')}%")
    lines.append(f"  금리차  {d.get('yield_spread', 'N/A')}%{inv_str}")

    # 채권/신용
    lines.append("【채권/신용】")
    lines.append(f"  MOVE        {d.get('MOVE', 'N/A')}")
    lines.append(f"  TED 스프레드 {d.get('TED_spread', 'N/A')}%")

    # 섹터
    lines.append("【섹터 TOP3 (1주 수익률)】")
    for r in d.get('sector_ranking', [])[:3]:
        lines.append(f"  {r['ticker']} {r['name']}  {r['ret_1w']:+.2f}%" if r['ret_1w'] is not None else f"  {r['ticker']} N/A")
    lines.append(f"  → {d.get('sector_risk_mode', 'N/A')}")

    # 비율 지표
    lines.append("【스타일/규모 비율】")
    for key, label in [('QQQ_SPY', 'QQQ/SPY'), ('IVW_IVE', 'IVW/IVE'), ('IWM_SPY', 'IWM/SPY')]:
        rd = d.get(key)
        if rd:
            ma_str = "▲MA20위" if rd['above_ma20'] else "▼MA20아래"
            lines.append(f"  {label}  {rd['ratio']}  {ma_str}  주간 {rd['chg_1w']:+.2f}%" if rd['chg_1w'] is not None else f"  {label}  {rd['ratio']}  {ma_str}")

    # 신용잔고
    lines.append("【신용잔고】")

    # 시장 전체 (상위 30종목 합산)
    mkt_cr = d.get('credit_market')
    if mkt_cr:
        total = mkt_cr.get('credit_total_bil', 0)
        count = mkt_cr.get('credit_stock_count', 0)
        lines.append(f"  코스피 상위{count}종목 합산  {total:,}억")
    else:
        lines.append(f"  코스피 합산  N/A")

    # 종목별 (삼성전자 + SK하이닉스)
    sam_cr = d.get('credit_samsung')
    hyn_cr = d.get('credit_hynix')
    for label, cr in [('삼성전자', sam_cr), ('SK하이닉스', hyn_cr)]:
        if cr:
            try:
                amt  = int(str(cr['loan_rmnd_amt']).replace(',','')) // 100000
                rate = cr['loan_rmnd_rate']
                lines.append(f"  {label}  {amt:,}억  잔고율 {rate}%")
            except Exception:
                lines.append(f"  {label}  데이터 오류")
        else:
            lines.append(f"  {label}  N/A")

    lines.append("─" * 30)

    # 이상 신호 / 종합 판단
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
            count = len(signals)
            if count >= 3:
                lines.append("\n⚠️ 종합 판단: 복수 경고 신호 동시 발생, 리스크 관리 필요")
            else:
                lines.append("\n⚠️ 종합 판단: 일부 지표 이상 신호, 주의 요망")
    else:
        lines.append("✅ 종합 판단: 이번 주 전반적 안정, 특이 신호 없음")

    # 차트 안내
    lines.append("")
    lines.append("📊 섹터 차트는 아래 이미지 참조")

    return "\n".join(lines)


# ─────────────────────────────────────────
# 텔레그램 발송 (텍스트 + 이미지)
# ─────────────────────────────────────────
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:3997] + "..."
    resp = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    if resp.status_code != 200:
        print(f"[오류] 텍스트 발송: {resp.text}")


def send_telegram_photo(img_buf, caption="섹터 ETF 주간 수익률"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    img_buf.seek(0)
    resp = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption},
                         files={'photo': ('chart.png', img_buf, 'image/png')})
    if resp.status_code != 200:
        print(f"[오류] 이미지 발송: {resp.text}")
    else:
        print("[완료] 이미지 발송 성공")


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────
def main():
    data = collect_all_weekly()
    signals = detect_signals_weekly(data)
    print(f"[신호] {len(signals)}개 감지됨")

    interpretation = get_claude_interpretation_weekly(data, signals)
    message = build_message_weekly(data, signals, interpretation)
    print(message)

    send_telegram_message(message)

    # 섹터 차트 발송
    chart_buf = build_sector_chart(data.get('sector_ranking', []))
    if chart_buf:
        send_telegram_photo(chart_buf)
        print("[완료] 차트 발송 성공")


if __name__ == '__main__':
    main()
