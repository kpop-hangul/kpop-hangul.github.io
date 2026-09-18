"""Offline regression tests: a push is not a verified publication."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from integrations.github_publisher import GitHubPublisher
from integrations.deployment_verifier import DeploymentVerifier
from modules.draft_queue import DraftApprovalQueue, approval_is_current
from modules.publication_workflow import submit, reconcile


def article():
    return {"title": "검증할 글", "description": "공개 배포 검증", "category": "개발 & 테크", "slug": "test-post",
            "markdown_content": "## 실제 확인\n원본 예제와 결과를 확인합니다.", "tags": [], "faqs": [],
            "heroImage": "/images/test.png"}


class PublicationStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"; self.root.mkdir()
        self.remote = Path(self.tmp.name) / "remote.git"
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Offline Test")
        self.git("config", "user.email", "offline@example.invalid")
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True, capture_output=True)
        self.git("remote", "add", "origin", str(self.remote))
        image = self.root / "blog-frontend/public/images/test.png"
        image.parent.mkdir(parents=True); image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        self.config = {"site": {"url": "https://example.github.io"}, "github": {
            "repo_root": str(self.root), "blog_content_dir": str(self.root / "blog"),
            "auto_git_commit": True, "auto_git_push": True}}
        self.queue = DraftApprovalQueue(str(self.root / "queue.json"))
        self.id = self.queue.add_draft(article(), {"total_score": 0})
        self.verifier = Mock()
        self.verifier.return_value.check.return_value = {"status": "verified", "commit_sha": "a" * 40}

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

    def submit(self):
        return submit(self.config, self.id, self.queue, GitHubPublisher, human_approved=True)

    def reconcile(self, **kwargs):
        return reconcile(self.config, self.id, self.queue, GitHubPublisher, verifier_factory=self.verifier, **kwargs)

    def attach_image_review_gate(self):
        payload=article()
        review={'decision':'pass','rights':'clear','issues':[],'original_value':'실행 가능한 원본 예제',
                'coverage_checked':True,'requires_expert_review':False,
                'claims':[{'source_id':'source-a','claim':'원본 예제와 결과를 확인합니다.',
                           'quote':'이 문서는 원본 예제와 결과를 확인하는 절차를 설명합니다.','assessment':'supported'}]}
        digest=lambda value: hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        image=self.root/'blog-frontend/public/images/test.png'
        payload['operations']={'workflow_id':'image-binding-fixture','review':review,'gate':{
            'status':'passed','article_hash':digest(payload),'review_hash':digest(review),
            'evidence_ids':['source-a'],'checked_at':'2026-09-18T00:00:00+00:00',
            'image_manifest':[{'url':'/images/test.png','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]}}
        self.queue.update_draft_content(self.id,payload)
        return image

    def test_manifested_revision_can_complete_verified_publication(self):
        self.attach_image_review_gate()
        self.assertFalse(self.submit()[0])
        self.assertEqual(self.queue.get_draft(self.id)['status'],'deployment_pending')
        self.assertTrue(self.reconcile()[0])

    def test_image_replaced_between_review_and_submission_never_commits(self):
        image=self.attach_image_review_gate();image.write_bytes(b'changed after review')
        with patch.object(GitHubPublisher,'_commit_paths') as commit,patch.object(GitHubPublisher,'_push_commit') as push:
            self.assertFalse(self.submit()[0]);commit.assert_not_called();push.assert_not_called()
        self.assertFalse((self.root/'blog').exists())

    def test_image_mutation_during_commit_is_detected_before_push(self):
        image=self.attach_image_review_gate()
        original=GitHubPublisher._commit_paths
        def change_during_commit(publisher,*args,**kwargs):
            image.write_bytes(b'changed between manifest hash and git add')
            return original(publisher,*args,**kwargs)
        with patch.object(GitHubPublisher,'_commit_paths',new=change_during_commit),patch.object(GitHubPublisher,'_push_commit') as push:
            self.assertFalse(self.submit()[0]);push.assert_not_called()
        self.assertEqual(self.queue.get_draft(self.id)['status'],'approved')
        self.assertNotIn('pushed_at',self.queue.get_draft(self.id)['publication'])

    def test_push_waits_for_exact_live_verification_then_notifies_once(self):
        self.assertFalse(self.submit()[0])
        draft = self.queue.get_draft(self.id)
        self.assertEqual(draft["status"], "deployment_pending")
        self.assertEqual(draft["publication"]["commit_sha"], self.git("rev-parse", "HEAD"))
        self.assertTrue(approval_is_current(draft))
        self.assertFalse(self.queue.mark_published(self.id, "test-post"))
        after, notify = Mock(), Mock()
        self.assertTrue(self.reconcile(after_verified=after, notify=notify)[0])
        self.assertTrue(self.reconcile(after_verified=after, notify=notify)[0])
        self.assertEqual(self.queue.get_draft(self.id)["status"], "published")
        after.assert_called_once(); notify.assert_called_once()

    def test_push_failure_retry_uses_one_saved_commit_and_post(self):
        with patch.object(GitHubPublisher, "_push_commit", side_effect=RuntimeError("https://secret@github.com")):
            ok, message = self.submit()
        self.assertFalse(ok); self.assertNotIn("secret", message)
        before = self.queue.get_draft(self.id)
        self.assertEqual(before["status"], "approved")
        self.assertTrue(before["publication"]["commit_sha"])
        self.assertFalse(self.submit()[0])
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")
        self.assertEqual(len(list((self.root / "blog").glob("*.md"))), 1)
        self.assertEqual(self.queue.get_draft(self.id)["publication"]["commit_sha"], before["publication"]["commit_sha"])

    def test_no_retry_push_or_new_commit_while_verification_pending(self):
        self.submit()
        self.verifier.return_value.check.return_value = {"status": "pending", "message": "CDN pending"}
        notify = Mock()
        with patch.object(GitHubPublisher, "_push_commit") as push, patch.object(GitHubPublisher, "_commit_paths") as commit:
            self.assertFalse(self.reconcile(notify=notify)[0])
            self.assertFalse(self.reconcile(notify=notify)[0])
            push.assert_not_called(); commit.assert_not_called(); notify.assert_not_called()
        self.assertEqual(self.queue.get_draft(self.id)["status"], "deployment_pending")

    def test_approval_fingerprint_binds_metadata_and_invalidates_on_edit(self):
        self.queue.mark_approved(self.id)
        self.assertTrue(approval_is_current(self.queue.get_draft(self.id)))
        self.queue.update_draft_content(self.id, {"title": "Changed title"})
        draft = self.queue.get_draft(self.id)
        self.assertEqual(draft["status"], "pending_review")
        self.assertNotIn("approved_fingerprint", draft)
        self.assertFalse(self.reconcile()[0])

    def test_button_revision_is_rechecked_inside_submission_boundary(self):
        from modules.draft_queue import article_review_token
        old_token = article_review_token(article())
        self.queue.update_draft_content(self.id, {"title": "changed after the button was rendered"})
        result = submit(self.config, self.id, self.queue, GitHubPublisher, human_approved=True, expected_review_token=old_token)
        self.assertFalse(result[0])
        self.assertEqual(self.queue.get_draft(self.id)["status"], "pending_review")
        self.assertFalse((self.root / "blog").exists())

    def test_out_of_band_change_does_not_inherit_approval(self):
        self.queue.mark_approved(self.id)
        path = Path(self.queue.queue_file); data = json.loads(path.read_text())
        data[0]["article"]["heroImage"] = "/images/other.png"
        path.write_text(json.dumps(data))
        self.assertFalse(self.submit()[0]); self.assertFalse(self.reconcile()[0])
        self.assertFalse((self.root / "blog").exists())

    def test_committed_inflight_draft_cannot_be_edited_or_rejected(self):
        self.submit()
        self.assertFalse(self.queue.update_draft_content(self.id, {"title": "Changed"}))
        self.assertFalse(self.queue.mark_rejected(self.id))

    def test_record_save_failure_after_commit_prevents_push(self):
        original = self.queue.record_publication
        def save(draft_id, value, status=None):
            return False if value.get("commit_sha") else original(draft_id, value, status)
        with patch.object(self.queue, "record_publication", side_effect=save), patch.object(GitHubPublisher, "_push_commit") as push:
            self.assertFalse(self.submit()[0]); push.assert_not_called()
        self.assertFalse(self.submit()[0])
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_disabled_git_cannot_claim_publication(self):
        self.config["github"]["auto_git_push"] = False
        self.assertFalse(self.submit()[0]); self.assertFalse((self.root / "blog").exists())

    def test_duplicate_check_ignores_internal_revision_marker(self):
        self.submit()
        changed = {**article(), "slug": "duplicate", "title": "Another title"}
        with self.assertRaisesRegex(ValueError, "본문이 같습니다"):
            GitHubPublisher(self.config).publish_article(changed, human_approved=True)


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40; self.revision = "b" * 64
        self.image = b"fixture png"
        self.record = {"commit_sha": self.sha, "pushed_at": "now", "revision": self.revision,
                       "url": "https://example.github.io/blog/test/", "assets": [
                           {"url": "/images/test.png", "sha256": hashlib.sha256(self.image).hexdigest()}]}
        self.run = {"head_sha": self.sha, "id": 123, "run_number": 1, "run_attempt": 1,
                    "status": "completed", "conclusion": "success"}
        self.page = f'<span data-publication-revision="{self.revision}" hidden></span><img src="/images/test.png">'
        self.session = Mock()
        self.repo_patch = patch("integrations.deployment_verifier.github_repository", return_value="owner/repo")
        self.repo_patch.start(); self.addCleanup(self.repo_patch.stop)
        self.verifier = DeploymentVerifier({"site": {"url": "https://example.github.io"}}, "/tmp", self.session)

    def response(self, content, kind):
        value = Mock(status_code=200, headers={"Content-Type": kind})
        value.iter_content.return_value = [content if isinstance(content, bytes) else content.encode()]
        return value

    def check(self, runs=None, page=None, image=None):
        self.session.get.side_effect = [self.response(json.dumps({"workflow_runs": runs if runs is not None else [self.run]}), "application/json"),
                                       self.response(self.page if page is None else page, "text/html"),
                                       self.response(self.image if image is None else image, "image/png")]
        return self.verifier.check(self.record)

    def test_only_exact_successful_sha_plus_page_revision_and_image_hash_is_verified(self):
        self.assertEqual(self.check()["status"], "verified")
        for call in self.session.get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(len(self.session.get.call_args_list), 3)  # no script, ad, or analytics fetch

    def test_other_commit_success_cannot_verify(self):
        self.assertEqual(self.check(runs=[{**self.run, "head_sha": "c" * 40}])["status"], "pending")
        self.assertEqual(self.session.get.call_count, 1)

    def test_failed_and_running_pages_cannot_verify(self):
        self.assertEqual(self.check(runs=[{**self.run, "conclusion": "failure"}])["status"], "failed")
        self.assertEqual(self.check(runs=[{**self.run, "status": "in_progress"}])["status"], "pending")

    def test_stale_page_or_missing_or_changed_image_cannot_verify(self):
        self.assertEqual(self.check(page="<h1>old article</h1>")["status"], "pending")
        self.assertEqual(self.check(page=f'<span data-publication-revision="{self.revision}" hidden></span>')["status"], "pending")
        self.assertEqual(self.check(image=b"different bytes")["status"], "pending")

    def test_network_exception_does_not_leak_credentials(self):
        self.session.get.side_effect = RuntimeError("https://SECRET@github.com")
        result = self.verifier.check(self.record)
        self.assertEqual(result["status"], "pending"); self.assertNotIn("SECRET", str(result))


class GenerationGuardTests(unittest.TestCase):
    def test_disabled_legacy_generation_never_instantiates_model(self):
        import main_pipeline
        cfg = {"operations": {"legacy_generation_enabled": False}}
        with patch.object(main_pipeline, "ContentWriter") as writer, patch.object(main_pipeline, "KeywordHarvester") as harvester:
            main_pipeline.run_auto_pipeline(cfg)
            main_pipeline.run_dryrun_pipeline(cfg)
            main_pipeline.run_geeknews_weekly_pipeline(cfg)
            writer.assert_not_called(); harvester.assert_not_called()

    def test_sitemap_check_never_calls_retired_search_engine_ping(self):
        from integrations.google_indexing import GoogleIndexing
        response = Mock(status_code=200, content=b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></sitemapindex>')
        with patch("integrations.google_indexing.requests.get", return_value=response) as get:
            result = GoogleIndexing({"site": {"url": "https://example.github.io"}}).check_sitemap()
        self.assertTrue(result["available"]); self.assertEqual(result["indexing_status"], "unknown")
        self.assertEqual(get.call_args.args[0], "https://example.github.io/sitemap-index.xml")


if __name__ == "__main__":
    unittest.main()
