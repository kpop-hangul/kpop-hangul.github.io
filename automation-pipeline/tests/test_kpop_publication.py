import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from modules.draft_queue import DraftApprovalQueue
from integrations.github_publisher import GitHubPublisher
import daily_kpop_pipeline as pipeline


def lesson():
    return {'title':'Learning lesson','description':'A Korean vocabulary lesson','category':'Beginner (Level 1)',
            'songTitle':'Song','artist':'Artist','genre':'Dance & Pop','difficulty':'Beginner',
            'markdown_content':'## Vocabulary\nOriginal examples to practise Korean words.', 'tags':[], 'faqs':[], 'slug':'test-song'}

class KpopPublication(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.queue=DraftApprovalQueue(str(self.root/'queue.json'))
        self.config={'github':{'repo_root':str(self.root),'blog_content_dir':str(self.root/'blog'),'auto_git_commit':True,'auto_git_push':True},'site':{'url':'https://example.invalid'}}
        self.id=self.queue.add_draft(lesson(),{'total_score':0},topic={'artist':'Artist','title':'Song'})
        self.q=patch.object(pipeline,'DraftApprovalQueue',return_value=self.queue);self.q.start();self.addCleanup(self.q.stop)
        self.song=patch.object(pipeline,'save_published_song');self.record=self.song.start();self.addCleanup(self.song.stop)
        self.notify=patch.object(pipeline,'TelegramNotifier');self.notifier=self.notify.start();self.addCleanup(self.notify.stop)

    def test_push_failure_preserves_queue_and_no_success_side_effects(self):
        with patch.object(GitHubPublisher,'_commit_paths',side_effect=RuntimeError('push rejected')):
            success,_=pipeline.publish_queued_draft(self.config,self.id,human_approved=True)
        self.assertFalse(success);self.assertEqual(self.queue.get_draft(self.id)['status'],'approved')
        self.record.assert_not_called();self.notifier.assert_not_called()

    def test_retry_same_revision_after_failed_push(self):
        with patch.object(GitHubPublisher,'_commit_paths',side_effect=RuntimeError('push rejected')):
            pipeline.publish_queued_draft(self.config,self.id,human_approved=True)
        with patch.object(GitHubPublisher,'_commit_paths') as git:
            success,url=pipeline.publish_queued_draft(self.config,self.id,human_approved=True)
        self.assertTrue(success);self.assertIn('/blog/test-song/',url)
        self.assertEqual(self.queue.get_draft(self.id)['status'],'published');git.assert_called_once()
        self.record.assert_called_once();self.notifier.return_value.send_article_published.assert_called_once()

    def test_rejected_or_unapproved_cannot_publish(self):
        self.assertFalse(pipeline.publish_queued_draft(self.config,self.id)[0])
        self.queue.mark_rejected(self.id)
        self.assertFalse(pipeline.publish_queued_draft(self.config,self.id,human_approved=True)[0])
        self.assertFalse((self.root/'blog').exists())

    def test_invalid_lesson_cannot_write_content(self):
        self.queue.update_draft_content(self.id,{'difficulty':'expert'})
        self.assertFalse(pipeline.publish_queued_draft(self.config,self.id,human_approved=True)[0])
        self.assertFalse((self.root/'blog').exists())

    def test_failed_queue_update_after_push_does_not_notify_success(self):
        with patch.object(GitHubPublisher,'_commit_paths'),patch.object(self.queue,'mark_published',return_value=False):
            self.assertFalse(pipeline.publish_queued_draft(self.config,self.id,human_approved=True)[0])
        self.notifier.assert_not_called()

    def test_legacy_queue_slug_is_preserved_without_treating_new_post_as_update(self):
        path=Path(self.queue.queue_file);data=json.loads(path.read_text());data[0]['existing_slug']='test-song';path.write_text(json.dumps(data))
        with patch.object(GitHubPublisher,'_commit_paths'):
            self.assertTrue(pipeline.publish_queued_draft(self.config,self.id,human_approved=True)[0])
        self.assertTrue((self.root/'blog/test-song.md').is_file())

    def test_image_refresh_queues_full_article_without_overwriting_post(self):
        import manage_kpop
        directory = self.root/'automation-pipeline'
        directory.mkdir()
        posts = self.root/'blog-frontend/src/content/blog'
        posts.mkdir(parents=True)
        path = posts/'test-song.md'
        original = '---\ntitle: Existing song\ndescription: Korean lesson\n---\n## Words\nOriginal body'
        path.write_text(original)
        with patch.object(manage_kpop, 'PIPELINE_DIR', str(directory)), \
             patch.object(pipeline, 'load_config', return_value=self.config), \
             patch('modules.gpt_images.prepare_article_images', side_effect=lambda article, config: article) as images, \
             patch('agents.editorial_reviewer.EditorialReviewAgent') as reviewer, \
             patch('modules.draft_queue.DraftApprovalQueue', return_value=self.queue):
            reviewer.return_value.review_article.return_value = {'total_score': 0}
            manage_kpop.cmd_images()
        self.assertEqual(path.read_text(), original)
        article = images.call_args.args[0]
        self.assertEqual(article['title'], 'Existing song')
        self.assertIn('Original body', article['markdown_content'])
        queued = self.queue.list_pending()[-1]
        self.assertEqual(queued['existing_slug'], 'test-song')
        self.assertEqual(queued['status'], 'pending_review')

if __name__=='__main__':unittest.main()
