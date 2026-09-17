"""Offline contracts for GPT routing, contextual assets and durable queues."""
import concurrent.futures
import hashlib
import json
import multiprocessing
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from integrations.gpt_runner import GPTRunner, GenerationError
from integrations.github_publisher import GitHubPublisher
from modules import gpt_images
from modules.draft_queue import DraftApprovalQueue
from modules.content_validation import body_fingerprint, ContentValidationError


def draft():
    return {'title':'초안 검토','description':'승인 전 확인할 사항','category':'개발 & 테크','tags':[], 'faqs':[],
            'slug':'2026-09-17-검토', 'markdown_content':'## 본문 검토\n출처를 확인합니다.\n\n## 이미지 검토\n본문과 일치하는지 확인합니다.'}


def append_queue(args):
    path,index=args
    return DraftApprovalQueue(path).add_draft(draft(),{'total_score':0},topic={'index':index})


class GPTContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.config={'engine':{'provider':'codex_cli','cli_command':'codex'},'agent':{'model_name':'gpt-6-astra','effort':'high'},'image_agent':{'orchestrator_model':'gpt-6-astra'}}

    def test_text_routes_explicit_model_and_no_tools(self):
        seen={}
        def run(command,**kwargs):
            seen.update(command=command,kwargs=kwargs)
            Path(command[command.index('--output-last-message')+1]).write_text('{"ok":true}')
            return Mock(returncode=0)
        with patch('integrations.gpt_runner.shutil.which',return_value='/bin/codex'),patch('integrations.gpt_runner.subprocess.run',side_effect=run):
            self.assertEqual(GPTRunner(self.config).generate_text('system','input'),'{"ok":true}')
        self.assertEqual(seen['command'][seen['command'].index('-m')+1],'gpt-6-astra')
        self.assertIn('read-only',seen['command']);self.assertIn('shell_tool',seen['command'])
        self.assertIn('model_reasoning_effort="high"',seen['command'])
        self.assertEqual(seen['kwargs']['input'].count('[EDITORIAL INPUT]'),1)

    def test_failure_does_not_retry_other_provider(self):
        with patch('integrations.gpt_runner.shutil.which',return_value='/bin/codex'),patch('integrations.gpt_runner.subprocess.run',return_value=Mock(returncode=1)) as call:
            with self.assertRaises(GenerationError):GPTRunner(self.config).generate_text('system','input')
            self.assertEqual(call.call_count,1)

    def test_non_gpt_model_is_rejected(self):
        with self.assertRaises(GenerationError):GPTRunner(self.config).generate_text('system','input',model_name='gemini-test')

    def test_missing_cli_has_actionable_error(self):
        with patch.object(GPTRunner,'get_cli_path',return_value=None):
            with self.assertRaisesRegex(GenerationError,'codex login'):GPTRunner(self.config).generate_text('system','input')

    def test_image_path_is_not_arbitrary_file(self):
        secret=self.root/'other.png';secret.write_bytes(b'not an image')
        with patch.object(GPTRunner,'_run',return_value=json.dumps({'image_path':str(secret)})):
            with self.assertRaises(GenerationError):GPTRunner(self.config).generate_image('test')

    def fake_image(self, prompt):
        self.prompts.append(prompt)
        path=self.root/f'generated-{len(self.prompts)}.png'
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+b'test-image-fixture')
        return path

    def test_three_contextual_images_cached_and_bound_to_content(self):
        self.prompts=[]
        with patch.object(gpt_images,'PUBLIC',self.root/'public'),patch.object(GPTRunner,'generate_image',side_effect=self.fake_image):
            result=gpt_images.prepare_article_images(draft(),self.config)
            assets=gpt_images.referenced_assets(result,self.root/'public')
            self.assertEqual(len(assets),3)
            self.assertEqual(len(self.prompts),3)
            self.assertIn('출처를 확인',self.prompts[1])
            self.assertIn('본문과 일치',self.prompts[2])
            self.assertEqual(body_fingerprint(draft()['markdown_content']),body_fingerprint(result['markdown_content']))
            again=gpt_images.prepare_article_images(result,self.config)
            self.assertEqual(len(self.prompts),3)
            self.assertEqual(result['heroImage'],again['heroImage'])
            result['markdown_content']+='\n새로운 내용'
            changed=gpt_images.prepare_article_images(result,self.config)
            self.assertEqual(len(self.prompts),6)
            self.assertNotEqual(changed['heroImage'],again['heroImage'])

    def test_image_failure_never_returns_svg_placeholder(self):
        with patch.object(gpt_images,'PUBLIC',self.root/'public'),patch.object(GPTRunner,'generate_image',side_effect=GenerationError('unavailable')):
            with self.assertRaises(GenerationError):gpt_images.prepare_article_images(draft(),self.config)
            self.assertEqual(list((self.root/'public').rglob('*.svg')),[])

    def test_missing_and_escaping_assets_fail(self):
        for url in ['/images/missing.png','/images/../../../other.png']:
            with self.assertRaises((ValueError,FileNotFoundError)):
                gpt_images.referenced_assets({**draft(),'heroImage':url},self.root/'public')

    def test_image_generation_cannot_be_claimed_after_body_edit(self):
        article=draft();article['image_generation']={'status':'complete','content_identity':gpt_images.image_identity(article)}
        article['markdown_content']+=' CHANGED'
        pub=GitHubPublisher({'github':{'repo_root':str(self.root),'blog_content_dir':str(self.root/'blog'),'auto_git_commit':False}})
        with self.assertRaises(ContentValidationError):pub.publish_article(article,human_approved=True)

    def test_assets_are_committed_with_post_without_unrelated_staged_changes(self):
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        for key,val in [('user.name','Test'),('user.email','test@example.invalid')]:subprocess.run(['git','-C',str(self.root),'config',key,val],check=True)
        unrelated=self.root/'unrelated.txt';unrelated.write_text('unrelated')
        subprocess.run(['git','-C',str(self.root),'add','unrelated.txt'],check=True)
        pubdir=self.root/'blog-frontend/public';self.prompts=[]
        with patch.object(gpt_images,'PUBLIC',pubdir),patch.object(GPTRunner,'generate_image',side_effect=self.fake_image):
            article=gpt_images.prepare_article_images(draft(),self.config)
        cfg={'github':{'repo_root':str(self.root),'blog_content_dir':str(self.root/'blog-frontend/src/content/blog'),'auto_git_commit':True,'auto_git_push':False}}
        GitHubPublisher(cfg).publish_article(article,human_approved=True)
        committed=subprocess.check_output(['git','-C',str(self.root),'ls-tree','-r','--name-only','HEAD'],text=True)
        self.assertEqual(committed.count('.png'),3);self.assertNotIn('unrelated.txt',committed)
        self.assertIn('unrelated.txt',subprocess.check_output(['git','-C',str(self.root),'diff','--cached','--name-only'],text=True))

    def test_concurrent_queue_writes_do_not_lose_drafts(self):
        path=str(self.root/'queue.json')
        with concurrent.futures.ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork')) as pool:
            ids=list(pool.map(append_queue,[(path,i) for i in range(24)]))
        self.assertEqual(len(set(ids)),24)
        self.assertEqual(len(json.loads(Path(path).read_text())),24)

    def test_queue_directory_entrypoints_share_one_file(self):
        pipeline = self.root/'automation-pipeline'
        pipeline.mkdir()
        expected = str(pipeline/'data/draft_queue.json')
        self.assertEqual(DraftApprovalQueue(str(self.root)).queue_file, expected)
        self.assertEqual(DraftApprovalQueue(str(pipeline)).queue_file, expected)
        self.assertEqual(DraftApprovalQueue(expected).queue_file, expected)

    def test_corrupt_queue_is_preserved(self):
        path=self.root/'queue.json';path.write_text('{broken')
        with self.assertRaises(ValueError):DraftApprovalQueue(str(path)).add_draft(draft(),{'total_score':0})
        self.assertEqual(path.read_text(),'{broken')

    def test_failed_atomic_replace_preserves_old_queue(self):
        path=self.root/'queue.json';q=DraftApprovalQueue(str(path));q.add_draft(draft(),{'total_score':0});old=path.read_bytes()
        with patch('modules.atomic_storage.os.replace',side_effect=OSError('disk failed')):
            with self.assertRaises(OSError):q.add_draft(draft(),{'total_score':0})
        self.assertEqual(path.read_bytes(),old)

    def test_ambiguous_id_rejected_and_edit_requires_new_approval(self):
        q=DraftApprovalQueue(str(self.root/'queue.json'));first=q.add_draft(draft(),{'total_score':0});q.add_draft(draft(),{'total_score':0})
        with self.assertRaises(ValueError):q.mark_rejected('draft_')
        q.mark_approved(first);q.update_draft_content(first,{'title':'수정된 글'})
        item=q.get_draft(first);self.assertEqual(item['status'],'pending_review');self.assertNotIn('approved_at',item)
        self.assertEqual(item['article']['markdown_content'],draft()['markdown_content'])

if __name__=='__main__':unittest.main()
