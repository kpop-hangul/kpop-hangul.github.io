"""Read-only, site-scoped AdSense v2 reports; never synthesize missing metrics.

API contracts:
https://developers.google.com/adsense/management/reference/rest/v2/accounts.reports/generate
https://developers.google.com/adsense/management/reference/rest/v2/ReportResult
https://developers.google.com/adsense/management/reporting/filtering
"""
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit


class GoogleAdSenseAPI:
    SCOPES = ["https://www.googleapis.com/auth/adsense.readonly"]
    METRICS = ["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS", "IMPRESSIONS_CTR",
               "IMPRESSIONS_RPM", "PAGE_VIEWS", "PAGE_VIEWS_RPM"]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adsense = config.get("adsense", {})
        self.config_dir = str(Path(__file__).resolve().parents[1] / "config")
        self.token_path = str(Path(self.config_dir) / "adsense_token.json")
        self.service_account_path = str(Path(self.config_dir) / "adsense_service_account.json")
        self.publisher_id = str(self.adsense.get("publisher_id") or "").removeprefix("ca-")
        self.site_domain = None
        try:
            parsed = urlsplit(str(config.get("site", {}).get("url") or ""))
            if parsed.hostname and parsed.scheme in ("http", "https"):
                self.site_domain = parsed.hostname.lower().rstrip(".")
        except ValueError:
            pass
        self.account_name = f"accounts/{self.publisher_id}" if self.publisher_id else None

    def is_configured(self) -> bool:
        return Path(self.token_path).is_file() or Path(self.service_account_path).is_file()

    def _get_authenticated_service(self):
        from googleapiclient.discovery import build
        from google_auth_httplib2 import AuthorizedHttp
        import httplib2
        if Path(self.token_path).is_file():
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            if creds.expired and creds.refresh_token:
                # Refresh only in memory. Reporting does not rewrite credential files.
                creds.refresh(Request())
        elif Path(self.service_account_path).is_file():
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_path, scopes=self.SCOPES)
        else:
            return None
        http = AuthorizedHttp(creds, http=httplib2.Http(timeout=20))
        return build("adsense", "v2", http=http, cache_discovery=False)

    def _empty(self, status="unavailable", reason="credentials_missing") -> Dict[str, Any]:
        return {"status": status, "reason": reason, "source": "google_adsense_v2",
                "is_real_data": False, "site_domain": self.site_domain,
                "account_name": self.account_name, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "period": "TODAY", "month_period": "MONTH_TO_DATE", "month_status": "unavailable",
                "reporting_timezone": "ACCOUNT_TIME_ZONE", "account_timezone": None, "currency": None,
                "start_date": None, "end_date": None, "month_start_date": None, "month_end_date": None,
                "estimated_earnings": None, "month_total": None,
                "est_earnings_usd": None, "month_total_usd": None,
                "impressions": None, "clicks": None, "ctr": None, "rpm": None,
                "page_views": None, "page_rpm": None, "warnings": []}

    @staticmethod
    def _number(value, integer=False):
        if value is None or value == "" or isinstance(value, bool):
            return None
        try:
            result = float(value)
            if not math.isfinite(result) or (integer and (result < 0 or not result.is_integer())):
                return None
            return int(result) if integer else result
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value):
        try:
            return datetime(int(value["year"]), int(value["month"]), int(value["day"])).date().isoformat()
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def _parse_report(cls, report, metrics):
        # Map by returned names, not a presumed column order. No rows is unknown,
        # while explicit zero-valued totals/rows remains measured zero.
        headers = report.get("headers", [])
        row = report.get("totals")
        if not row:
            rows = report.get("rows", [])
            row = rows[0] if len(rows) == 1 else None
        if not row:
            return {"status": "no_data", "values": {}, "currency": None}
        cells = row.get("cells", [])
        if len(cells) != len(headers) or not headers:
            return {"status": "invalid_response", "values": {}, "currency": None}
        values = {}
        currencies = set()
        for header, cell in zip(headers, cells):
            name = header.get("name")
            if name in metrics:
                values[name] = cls._number(cell.get("value"), name in ("IMPRESSIONS", "CLICKS", "PAGE_VIEWS"))
                if name in ("ESTIMATED_EARNINGS", "IMPRESSIONS_RPM", "PAGE_VIEWS_RPM"):
                    currency = header.get("currencyCode")
                    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                        return {"status": "invalid_currency", "values": {}, "currency": None}
                    currencies.add(currency)
        if len(currencies) != 1:
            return {"status": "invalid_currency", "values": {}, "currency": None}
        status = "measured" if all(values.get(m) is not None for m in metrics) else "partial"
        return {"status": status, "values": values, "currency": next(iter(currencies))}

    def fetch_live_statistics(self) -> Dict[str, Any]:
        if not re.fullmatch(r"pub-\d{16}", self.publisher_id):
            return self._empty(reason="publisher_id_missing_or_invalid")
        if not self.site_domain or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", self.site_domain):
            return self._empty(reason="site_domain_missing_or_invalid")
        override = self.adsense.get("site_domain")
        if override and str(override).lower().rstrip(".") != self.site_domain:
            return self._empty(reason="site_domain_mismatch")
        if not self.is_configured():
            return self._empty()
        try:
            service = self._get_authenticated_service()
            if service is None:
                return self._empty()
            # Explicit account only. Never fall back to an arbitrary first account.
            account = service.accounts().get(name=self.account_name).execute()
            if account.get("name") != self.account_name:
                return self._empty(reason="account_mismatch")
            params = {"account": self.account_name,
                      "filters": [f"DOMAIN_CODE=={self.site_domain}"],
                      "reportingTimeZone": "ACCOUNT_TIME_ZONE"}
            reports = service.accounts().reports()
            today = reports.generate(**params, dateRange="TODAY", metrics=self.METRICS).execute()
            month = reports.generate(**params, dateRange="MONTH_TO_DATE", metrics=["ESTIMATED_EARNINGS"]).execute()
            parsed = self._parse_report(today, self.METRICS)
            parsed_month = self._parse_report(month, ["ESTIMATED_EARNINGS"])
            result = self._empty(status=parsed["status"], reason=None)
            currency = parsed["currency"] or parsed_month["currency"]
            if parsed["currency"] and parsed_month["currency"] and parsed["currency"] != parsed_month["currency"]:
                return self._empty(status="invalid_response", reason="currency_mismatch")
            values = parsed["values"]
            result.update({
                "is_real_data": parsed["status"] == "measured", "currency": currency,
                "month_status": parsed_month["status"],
                "account_timezone": (account.get("timeZone") or {}).get("id"),
                "estimated_earnings": values.get("ESTIMATED_EARNINGS"),
                "month_total": parsed_month["values"].get("ESTIMATED_EARNINGS"),
                "impressions": values.get("IMPRESSIONS"), "clicks": values.get("CLICKS"),
                "ctr": round(values["IMPRESSIONS_CTR"] * 100, 6) if values.get("IMPRESSIONS_CTR") is not None else None,
                "rpm": values.get("IMPRESSIONS_RPM"), "page_views": values.get("PAGE_VIEWS"),
                "page_rpm": values.get("PAGE_VIEWS_RPM"),
                "start_date": self._date(today.get("startDate")), "end_date": self._date(today.get("endDate")),
                "month_start_date": self._date(month.get("startDate")), "month_end_date": self._date(month.get("endDate")),
                "warnings": list(today.get("warnings", [])) + list(month.get("warnings", [])),
            })
            # Compatibility fields are populated only when the API confirms USD.
            if currency == "USD":
                result["est_earnings_usd"] = result["estimated_earnings"]
                result["month_total_usd"] = result["month_total"]
            return result
        except ImportError:
            return self._empty(status="unavailable", reason="dependency_missing")
        except Exception as exc:
            # API errors can contain URLs, account identifiers or credentials.
            return self._empty(status="error", reason=f"api_error:{type(exc).__name__}")
