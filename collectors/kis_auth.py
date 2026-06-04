"""
kis_auth.py
한국투자증권 Open API 인증 모듈
- Access Token 발급 (유효기간 24시간)
- GitHub Actions에서 매일 자동 발급
"""

import requests
import json
import os
from datetime import datetime


BASE_URL = "https://openapi.koreainvestment.com:9443"


def get_access_token(app_key, app_secret):
    """
    Access Token 발급
    매일 실행 시마다 새로 발급 (24시간 유효)
    """
    url = f"{BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    try:
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        token = data.get('access_token')
        if token:
            print(f"[KIS] Access Token 발급 성공 (만료: {data.get('access_token_token_expired', 'N/A')})")
            return token
        else:
            print(f"[KIS] Token 발급 실패: {data}")
            return None
    except Exception as e:
        print(f"[KIS] Token 발급 오류: {e}")
        return None


def get_kospi_index(app_key, app_secret, access_token):
    """
    코스피 지수 현재값 조회
    TR: FHKUP03500100 (국내업종기간별시세)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",  # 업종 현재가 (단순 조회)
        "content-type": "application/json"
    }
    params = {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd":         "0001"   # 0001 = 코스피
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        print(f"[KIS] 코스피 전체응답: {str(data)[:300]}")
        if data.get('rt_cd') == '0':
            output = data.get('output', {})
            # 필드명 후보 순서대로 시도
            current = None
            for key in ['bstp_nmix_prpr', 'stck_prpr', 'prpr']:
                if output.get(key):
                    try:
                        current = float(str(output[key]).replace(',', ''))
                        break
                    except Exception:
                        continue
            chg_rt = None
            for key in ['bstp_nmix_prdy_ctrt', 'prdy_ctrt']:
                if output.get(key):
                    try:
                        chg_rt = float(str(output[key]).replace(',', ''))
                        break
                    except Exception:
                        continue
            if current:
                return {
                    'KOSPI':        round(current, 2),
                    'KOSPI_1d_chg': round(chg_rt, 2) if chg_rt else None,
                    'KOSPI_source': 'KIS'
                }
        print(f"[KIS] 코스피 조회 실패: {data.get('msg1', '')} / 전체응답: {str(data)[:200]}")
        return None
    except Exception as e:
        print(f"[KIS] 코스피 조회 오류: {e}")
        return None


def get_market_investor_trend(app_key, app_secret, access_token):
    """
    국내 시장별 투자자 동향
    장 마감 후에도 당일 데이터 조회 가능한 TR코드 순서로 시도
    """
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')

    # TR코드 후보
    candidates = [
        {
            # 시장별 투자자매매동향(일별) [국내주식-075]
            # 장 마감 후에도 당일 데이터 조회 가능
            "url": f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
            "tr_id": "FHPTJ04040000",
            "params": {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD":         "0001",
                "FID_INPUT_DATE_1":       today,
                "FID_INPUT_ISCD_1":       "KSP",   # 코스피
                "FID_INPUT_DATE_2":       today,
                "FID_INPUT_ISCD_2":       "0001"
            }
        },
        {
            # 기존 TR코드 (장중만 작동, 마지막 시도)
            "url": f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor",
            "tr_id": "FHKST01010900",
            "params": {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd":         "0001"
            }
        }
    ]

    for c in candidates:
        print(f"[KIS] 투자자동향 시도: {c['tr_id']}")
        try:
            headers = {
                "authorization": f"Bearer {access_token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": c["tr_id"],
                "content-type": "application/json"
            }
            resp = requests.get(c["url"], headers=headers, params=c["params"], timeout=10)
            if not resp.text.strip():
                print(f"[KIS] {c['tr_id']}: 빈 응답")
                continue
            data = resp.json()
            print(f"[KIS] {c['tr_id']} 응답: rt_cd={data.get('rt_cd')} / {str(data)[:200]}")

            if data.get('rt_cd') != '0':
                continue

            output = data.get('output', data.get('output1', []))
            if isinstance(output, list):
                if not output:
                    print(f"[KIS] {c['tr_id']}: output 빈 리스트 → 다음 TR 시도")
                    continue
                o = output[0]
            elif isinstance(output, dict):
                o = output
            else:
                continue

            # 외국인 순매수 필드 탐색
            foreign = o.get('frgn_ntby_tr_pbmn')  # 외국인 순매수 거래대금
            if foreign is not None:
                print(f"[KIS] 투자자동향 수집 성공 (TR: {c['tr_id']})")
                return {
                    'foreign_net': o.get('frgn_ntby_tr_pbmn', 'N/A'),  # 외국인 순매수 거래대금
                    'inst_net':    o.get('orgn_ntby_tr_pbmn', 'N/A'),  # 기관계 순매수 거래대금
                    'indiv_net':   o.get('prsn_ntby_tr_pbmn', 'N/A')   # 개인 순매수 거래대금
                }
        except Exception as e:
            print(f"[KIS] {c['tr_id']} 오류: {e}")
            continue

    print("[KIS] 투자자동향: 모든 TR코드 실패")
    return None


def get_foreign_inst_top5(app_key, app_secret, access_token, investor='foreign'):
    """
    외국인 순매수 상위 5종목 (TR 오류로 임시 비활성화)
    시장 전체 동향은 get_market_investor_trend() 사용
    """
    return []


def get_stock_quote(app_key, app_secret, access_token, stock_code):
    """
    개별 종목 현재가 + 외국인 수급 조회
    stock_code: '005930' (삼성전자), '000660' (SK하이닉스)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",
        "content-type": "application/json"
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": stock_code
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get('rt_cd') == '0':
            o = data.get('output', {})
            return {
                'price':           o.get('stck_prpr', 'N/A'),
                'change_rate':     o.get('prdy_ctrt', 'N/A'),
                'foreign_rate':    o.get('hts_frgn_ehrt', 'N/A'),
                'foreign_net_buy': o.get('frgn_ntby_qty', 'N/A')
            }
        else:
            print(f"[KIS] {stock_code} 조회 실패: {data.get('msg1', '')}")
            return None
    except Exception as e:
        print(f"[KIS] {stock_code} 조회 오류: {e}")
        return None


def get_credit_balance(app_key, app_secret, access_token, stock_code):
    """
    종목별 신용잔고 일별추이 [국내주식-110]
    TR: FHPST04760000
    stock_code: '005930' (삼성전자), '000660' (SK하이닉스)
    """
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')

    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/daily-credit-balance"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST04760000",
        "content-type": "application/json"
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_cond_scr_div_code":  "20476",
        "fid_input_iscd":         stock_code,
        "fid_input_date_1":       today
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if not resp.text.strip():
            print(f"[KIS] 신용잔고 {stock_code}: 빈 응답")
            return None
        data = resp.json()
        if data.get('rt_cd') == '0':
            output = data.get('output', [])
            if not output:
                print(f"[KIS] 신용잔고 {stock_code}: 데이터 없음")
                return None
            # 가장 최근 데이터 (첫 번째 항목)
            o = output[0]
            return {
                'stock_code':    stock_code,
                'date':          o.get('deal_date', ''),
                'price':         o.get('stck_prpr', 'N/A'),
                'loan_new_amt':  o.get('whol_loan_new_amt', '0'),     # 융자 신규 금액
                'loan_rdmp_amt': o.get('whol_loan_rdmp_amt', '0'),    # 융자 상환 금액
                'loan_rmnd_amt': o.get('whol_loan_rmnd_amt', '0'),    # 융자 잔고 금액
                'loan_rmnd_rate': o.get('whol_loan_rmnd_rate', '0'),  # 융자 잔고 비율
                'loan_rmnd_stcn': o.get('whol_loan_rmnd_stcn', '0')  # 융자 잔고 주수
            }
        else:
            print(f"[KIS] 신용잔고 {stock_code} 실패: {data.get('msg1','')} / rt_cd={data.get('rt_cd')}")
            return None
    except Exception as e:
        print(f"[KIS] 신용잔고 {stock_code} 오류: {e}")
        return None


if __name__ == '__main__':
    # 테스트
    key    = os.environ.get('KIS_APP_KEY', '')
    secret = os.environ.get('KIS_APP_SECRET', '')
    if not key or not secret:
        print("KIS_APP_KEY, KIS_APP_SECRET 환경변수 필요")
    else:
        token = get_access_token(key, secret)
        if token:
            kospi = get_kospi_index(key, secret, token)
            print("코스피:", kospi)
            sam = get_stock_quote(key, secret, token, '005930')
            print("삼성전자:", sam)
