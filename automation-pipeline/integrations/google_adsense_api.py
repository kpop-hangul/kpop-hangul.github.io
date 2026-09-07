import os
import json
from typing import Dict, Any, Optional

class GoogleAdSenseAPI:
    """
    Google AdSense Management API (v2) 공식 연동 클라이언트
    실제 구글 애드센스 계정의 일일 수익, 노출수, 클릭수, RPM을 조회합니다.
    """

    SCOPES = ['https://www.googleapis.com/auth/adsense.readonly']

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config"))
        self.token_path = os.path.join(self.config_dir, "adsense_token.json")
        self.service_account_path = os.path.join(self.config_dir, "adsense_service_account.json")
        self.publisher_id = config.get("adsense", {}).get("publisher_id", "").replace("ca-", "")

    def is_configured(self) -> bool:
        """API 인증 정보 파일이 존재하는지 확인"""
        return os.path.exists(self.token_path) or os.path.exists(self.service_account_path)

    def _get_authenticated_service(self):
        """인증 자격증명을 로드하여 AdSense v2 서비스 객체 생성"""
        from googleapiclient.discovery import build
        
        # 1. OAuth2 User Token 우선 검사
        if os.path.exists(self.token_path):
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            
            creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_path, 'w', encoding='utf-8') as f:
                    f.write(creds.to_json())
            return build('adsense', 'v2', credentials=creds)

        # 2. Service Account Key 검사
        if os.path.exists(self.service_account_path):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_path, scopes=self.SCOPES
            )
            return build('adsense', 'v2', credentials=creds)

        return None

    def fetch_live_statistics(self) -> Optional[Dict[str, Any]]:
        """
        AdSense v2 API 호출: 오늘 당일 및 이번 달 누적 실시간 실적 조회
        """
        if not self.is_configured():
            return None

        try:
            service = self._get_authenticated_service()
            if not service:
                return None

            # 1. 계정 목록 확인 (accounts/pub-XXXXXXXXX)
            accounts_res = service.accounts().list().execute()
            accounts = accounts_res.get('accounts', [])
            if not accounts:
                print("⚠️ 연동된 AdSense 계정을 찾을 수 없습니다.")
                return None

            target_account = None
            if self.publisher_id:
                for acc in accounts:
                    if self.publisher_id in acc.get('name', ''):
                        target_account = acc['name']
                        break
            
            if not target_account:
                target_account = accounts[0]['name']

            # 2. 오늘 당일 실적 리포트 조회
            today_report = service.accounts().reports().generate(
                account=target_account,
                dateRange='TODAY',
                metrics=[
                    'ESTIMATED_EARNINGS',
                    'IMPRESSIONS',
                    'CLICKS',
                    'IMPRESSIONS_CTR',
                    'IMPRESSIONS_RPM'
                ]
            ).execute()

            est_earnings = 0.0
            impressions = 0
            clicks = 0
            ctr = 0.0
            rpm = 0.0

            rows = today_report.get('rows', [])
            if rows and len(rows) > 0:
                cells = rows[0].get('cells', [])
                # metrics 순서대로 매핑
                if len(cells) >= 5:
                    est_earnings = float(cells[0].get('value', 0.0) or 0.0)
                    impressions = int(cells[1].get('value', 0) or 0)
                    clicks = int(cells[2].get('value', 0) or 0)
                    ctr = round(float(cells[3].get('value', 0.0) or 0.0) * 100, 2)
                    rpm = float(cells[4].get('value', 0.0) or 0.0)

            # 3. 이번 달 누적 실적 리포트 조회
            month_report = service.accounts().reports().generate(
                account=target_account,
                dateRange='MONTH_TO_DATE',
                metrics=['ESTIMATED_EARNINGS']
            ).execute()

            month_total = 0.0
            m_rows = month_report.get('rows', [])
            if m_rows and len(m_rows) > 0:
                m_cells = m_rows[0].get('cells', [])
                if m_cells:
                    month_total = float(m_cells[0].get('value', 0.0) or 0.0)

            return {
                "is_real_data": True,
                "est_earnings_usd": round(est_earnings, 2),
                "month_total_usd": round(month_total, 2),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "rpm": round(rpm, 2)
            }

        except Exception as e:
            print(f"⚠️ AdSense API 실시간 호출 오류: {e}")
            return None
