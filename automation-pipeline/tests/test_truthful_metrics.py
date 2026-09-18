"""Offline regressions: unknown is not zero and repositories are not websites."""
import os
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agents.performance_tracker import PerformanceTracker
from integrations.google_adsense_api import GoogleAdSenseAPI
from integrations.telegram_bot import TelegramNotifier


PUB = 'pub-1234567890123456'
SITE = 'https://example.github.io'
CONFIG = {'adsense': {'publisher_id': 'ca-' + PUB}, 'site': {'url': SITE, 'title': '테스트'}}


def report(values=None, currency='KRW', totals=False):
    values = values if values is not None else {
        'CLICKS': '0', 'ESTIMATED_EARNINGS': '0', 'IMPRESSIONS': '0',
        'IMPRESSIONS_CTR': '0', 'PAGE_VIEWS_RPM': '0', 'PAGE_VIEWS': '0', 'IMPRESSIONS_RPM': '0'}
    headers = []
    for name in values:
        header = {'name': name}
        if name in ('ESTIMATED_EARNINGS', 'IMPRESSIONS_RPM', 'PAGE_VIEWS_RPM') and currency:
            header['currencyCode'] = currency
        headers.append(header)
    row = {'cells': [{'value': v} for v in values.values()]}
    result = {'headers': headers, 'startDate': {'year': 2026, 'month': 9, 'day': 18},
              'endDate': {'year': 2026, 'month': 9, 'day': 18}}
    result.update({'totals': row} if totals else {'rows': [row]})
    return result


class TruthfulMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        env_loader = patch('integrations.telegram_bot._load_env_file')
        env_loader.start()
        self.addCleanup(env_loader.stop)
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('offline test'))
        network.start()
        self.addCleanup(network.stop)
        urllib = patch('urllib.request.urlopen', side_effect=AssertionError('offline test'))
        urllib.start()
        self.addCleanup(urllib.stop)
        self.tracker = PerformanceTracker({'github': {'blog_content_dir': str(self.root)}})
        self.notifier = TelegramNotifier({'telegram': {'enabled': False}, 'site': {'url': SITE, 'title': 'A&B'}})
        self.notifier._send_message = Mock(return_value=True)

    def post(self, name, frontmatter):
        (self.root / (name + '.md')).write_text('---\n' + frontmatter + '\n---\nbody', encoding='utf-8')

    def api(self, today=None, month=None):
        api = GoogleAdSenseAPI(CONFIG)
        api.is_configured = Mock(return_value=True)
        service = Mock()
        service.accounts.return_value.get.return_value.execute.return_value = {'name': 'accounts/' + PUB}
        service.accounts.return_value.reports.return_value.generate.return_value.execute.side_effect = [
            today if today is not None else report(),
            month if month is not None else report({'ESTIMATED_EARNINGS': '0'})]
        api._get_authenticated_service = Mock(return_value=service)
        return api, service

    def test_inventory_excludes_drafts_and_does_not_call_mtime_a_publication(self):
        self.post('old', 'title: old\npubDate: 2020-01-01\ndraft: false')
        self.post('draft', 'title: draft\npubDate: ' + date.today().isoformat() + '\ndraft: true')
        self.post('today', 'title: today\npubDate: ' + date.today().isoformat())
        self.assertEqual(self.tracker.count_posts(), {'total': 2, 'today': 1, 'drafts': 1})
        self.assertEqual(len(self.tracker.get_post_details()), 2)

    def test_article_count_never_becomes_visits_or_indexed_pages(self):
        self.post('a', 'title: a')
        stats = self.tracker.get_site_statistics()
        self.assertIsNone(stats['est_pageviews'])
        self.assertIsNone(stats['indexed_pages'])
        self.assertEqual(stats['deployment_status'], 'not_checked')

    def test_github_credentials_and_tags_do_not_become_blog_measurements(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'not-a-real-token', 'PUBLIC_GA_ID': 'G-test'}):
            data = self.tracker.get_click_view_statistics()
        for key in ('today_views', 'today_uv', 'today_clicks', 'ctr', 'cumulative_views', 'growth_vs_yesterday'):
            self.assertIsNone(data[key])
        self.assertEqual(data['sources']['github']['status'], 'excluded')
        self.assertEqual(data['sources']['ga4']['status'], 'unavailable')
        self.assertEqual(data['top_posts'], [])
        self.assertEqual(data['category_views'], {})
        self.assertFalse(data['is_measured'])

    def test_legacy_history_is_not_read_or_overwritten(self):
        history = self.root / 'data' / 'traffic_history.json'
        history.parent.mkdir()
        history.write_text('{"old":{"today_views":999999,"is_measured":true}}')
        original = history.read_bytes()
        self.tracker.pipeline_dir = self.root
        self.tracker.get_click_view_statistics()
        self.assertEqual(history.read_bytes(), original)

    def test_tracker_uses_adsense_client_result_without_fallback(self):
        with patch('agents.performance_tracker.GoogleAdSenseAPI') as api:
            api.return_value.fetch_live_statistics.return_value = {'status': 'error', 'estimated_earnings': None}
            self.assertIsNone(self.tracker.get_adsense_statistics()['estimated_earnings'])
            api.assert_called_once_with(self.tracker.config)

    def test_missing_credentials_are_unavailable_not_zero(self):
        api = GoogleAdSenseAPI(CONFIG)
        api.is_configured = Mock(return_value=False)
        api._get_authenticated_service = Mock()
        result = api.fetch_live_statistics()
        self.assertEqual(result['reason'], 'credentials_missing')
        self.assertIsNone(result['estimated_earnings'])
        self.assertFalse(result['is_real_data'])
        api._get_authenticated_service.assert_not_called()

    def test_explicit_account_and_host_required(self):
        for config in ({'site': {'url': SITE}}, {'adsense': {'publisher_id': PUB}},
                       {'site': {'url': SITE}, 'adsense': {'publisher_id': PUB, 'site_domain': 'other.example'}}):
            api = GoogleAdSenseAPI(config)
            api._get_authenticated_service = Mock()
            result = api.fetch_live_statistics()
            self.assertIsNone(result['estimated_earnings'])
            api._get_authenticated_service.assert_not_called()

    def test_malformed_site_url_returns_unavailable(self):
        api = GoogleAdSenseAPI({'adsense': {'publisher_id': PUB}, 'site': {'url': 'https://['}})
        self.assertEqual(api.fetch_live_statistics()['reason'], 'site_domain_missing_or_invalid')

    def test_wrong_account_never_falls_back_to_first_account(self):
        api, service = self.api()
        service.accounts.return_value.get.return_value.execute.return_value = {'name': 'accounts/pub-9999999999999999'}
        result = api.fetch_live_statistics()
        self.assertEqual(result['reason'], 'account_mismatch')
        service.accounts.return_value.list.assert_not_called()
        service.accounts.return_value.reports.assert_not_called()

    def test_all_requests_are_filtered_to_exact_site_and_keep_returned_currency(self):
        api, service = self.api(report(totals=True))
        result = api.fetch_live_statistics()
        self.assertEqual(result['status'], 'measured')
        self.assertEqual(result['currency'], 'KRW')
        self.assertEqual(result['estimated_earnings'], 0)
        self.assertEqual(result['clicks'], 0)
        self.assertIsNone(result['est_earnings_usd'])
        self.assertEqual(result['start_date'], '2026-09-18')
        for call in service.accounts.return_value.reports.return_value.generate.call_args_list:
            self.assertEqual(call.kwargs['account'], 'accounts/' + PUB)
            self.assertEqual(call.kwargs['filters'], ['DOMAIN_CODE==example.github.io'])
            self.assertEqual(call.kwargs['reportingTimeZone'], 'ACCOUNT_TIME_ZONE')

    def test_header_name_mapping_and_explicit_usd_compatibility(self):
        values = {'CLICKS': '2', 'ESTIMATED_EARNINGS': '12.34', 'IMPRESSIONS': '80',
                  'IMPRESSIONS_CTR': '0.025', 'PAGE_VIEWS_RPM': '123.4', 'PAGE_VIEWS': '100', 'IMPRESSIONS_RPM': '154.25'}
        api, _ = self.api(report(values, 'USD'), report({'ESTIMATED_EARNINGS': '20.50'}, 'USD'))
        result = api.fetch_live_statistics()
        self.assertEqual(result['clicks'], 2)
        self.assertEqual(result['ctr'], 2.5)
        self.assertEqual(result['est_earnings_usd'], 12.34)
        self.assertEqual(result['month_total_usd'], 20.5)
        self.assertEqual(result['page_rpm'], 123.4)

    def test_empty_response_is_not_measured_zero(self):
        api, _ = self.api({'headers': [], 'rows': [], 'totalMatchedRows': '0'})
        result = api.fetch_live_statistics()
        self.assertEqual(result['status'], 'no_data')
        self.assertIsNone(result['estimated_earnings'])
        self.assertIsNone(result['clicks'])

    def test_missing_currency_does_not_assume_usd(self):
        api, _ = self.api(report(currency=None))
        result = api.fetch_live_statistics()
        self.assertEqual(result['status'], 'invalid_currency')
        self.assertIsNone(result['estimated_earnings'])

    def test_conflicting_currencies_rejected(self):
        api, _ = self.api(report(currency='USD'), report({'ESTIMATED_EARNINGS': '1'}, 'KRW'))
        result = api.fetch_live_statistics()
        self.assertEqual(result['reason'], 'currency_mismatch')
        self.assertIsNone(result['month_total'])

    def test_invalid_or_missing_metric_remains_none(self):
        values = {name: '0' for name in GoogleAdSenseAPI.METRICS}
        values['CLICKS'] = 'NaN'
        del values['IMPRESSIONS']
        api, _ = self.api(report(values))
        result = api.fetch_live_statistics()
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['clicks'])
        self.assertIsNone(result['impressions'])
        self.assertEqual(result['estimated_earnings'], 0)

    def test_error_is_unavailable_and_does_not_expose_exception_details(self):
        api, _ = self.api()
        api._get_authenticated_service.side_effect = RuntimeError('secret-token-contents')
        result = api.fetch_live_statistics()
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['clicks'])
        self.assertNotIn('secret-token-contents', str(result))

    def test_missing_optional_api_library_returns_explicit_status(self):
        api, _ = self.api()
        api._get_authenticated_service.side_effect = ImportError('googleapiclient')
        self.assertEqual(api.fetch_live_statistics()['reason'], 'dependency_missing')

    def test_unknown_renderers_do_not_crash_or_invent_zero(self):
        data = self.tracker.get_click_view_statistics()
        text = self.notifier.generate_click_view_report_text(data)
        self.assertIn('미수집', text)
        self.assertIn('A&amp;B', text)
        self.assertNotIn('0 회', text)
        self.notifier.send_daily_site_status('morning', self.tracker.get_site_statistics())
        self.notifier.send_adsense_daily_report(GoogleAdSenseAPI({}).fetch_live_statistics())
        self.assertNotIn('USD', self.notifier._send_message.call_args.args[0])

    def test_legacy_fabricated_github_statistics_not_rendered_as_measured(self):
        text = self.notifier.generate_click_view_report_text({
            'is_measured': True, 'today_views': 989898, 'today_clicks': 789789,
            'sources': {'github': {'status': '🟢 실측 연동됨'}}})
        self.assertNotIn('989,898', text)
        self.assertNotIn('789,789', text)

    def test_measured_zero_and_unknown_distinguished_in_renderers(self):
        text = self.notifier.generate_click_view_report_text({
            'status': 'measured', 'is_measured': True, 'source': 'ga4',
            'today_views': 0, 'today_uv': None})
        self.assertIn('페이지뷰: <b>0</b>', text)
        self.assertIn('순 방문자: <b>미수집</b>', text)
        api, _ = self.api()
        revenue = self.notifier.generate_adsense_report_text(api.fetch_live_statistics())
        self.assertIn('0.00 KRW', revenue)
        self.assertNotIn('USD', revenue)
        self.assertNotIn('1350', revenue)

    def test_health_missing_values_do_not_claim_running_services(self):
        self.notifier.send_health_report({})
        text = self.notifier._send_message.call_args.args[0]
        self.assertIn('미확인', text)
        self.assertNotIn('정상 활성', text)


if __name__ == '__main__':
    unittest.main()
