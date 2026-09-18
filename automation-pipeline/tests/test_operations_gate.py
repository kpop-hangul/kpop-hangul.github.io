"""Regression contracts for coordinator gate integrity at the publication boundary."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from modules.content_validation import ContentValidationError, validate_article
from integrations.github_publisher import GitHubPublisher


def reviewed_article():
    # These hashes were produced by the real blogops.content.validate_review gate.
    # Keep the fixture independent of the publication-side digest implementation.
    article = {'title':'실행 결과 확인 방법','description':'검토된 예제를 확인합니다.','category':'개발 & 테크',
               'slug':'verified-example','tags':['검토'],'faqs':[],'heroImage':'/images/verified.png',
               'markdown_content':'## 확인 절차\n입력 파일의 형식을 먼저 확인합니다.'}
    review = {'decision':'pass','issues':[],'rights':'clear','original_value':'사용자가 입력 형식을 확인할 수 있는 원본 예제',
              'claims':[{'source_id':'source-a','claim':'입력 파일의 형식을 먼저 확인합니다.',
                         'quote':'입력 파일을 열기 전에 문서의 데이터 형식을 확인합니다.','assessment':'supported'}],
              'coverage_checked':True,'requires_expert_review':False}
    article['operations'] = {'workflow_id':'workflow-fixture','review':review,'gate':{
        'status':'passed','article_hash':'eb91d1738dfa77568985b2f4c9e63202d3f25a3ab379a35c4a331d039623a7ae',
        'review_hash':'aab12c3b06796bd4ff9fbbef69b8ce418b89c05d815e249c91a9284d11b34057',
        'evidence_ids':['source-a'],'checked_at':'2026-09-18T02:34:24.037769+00:00'}}
    return article


def rehash_review(article):
    operations = article['operations']
    operations['gate']['review_hash'] = hashlib.sha256(json.dumps(operations['review'],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


class OperationsGateTests(unittest.TestCase):
    def test_actual_coordinator_gate_schema_and_hashes_are_accepted(self):
        article = reviewed_article()
        self.assertIs(validate_article(article),article)
        # Evidence collection may include relevant sources unused by an individual claim.
        article['operations']['gate']['evidence_ids'].append('additional-source')
        validate_article(article)

    def test_review_claim_can_refer_to_description(self):
        article=reviewed_article()
        article['operations']['review']['claims'][0]['claim']=article['description']
        rehash_review(article)
        validate_article(article)

    def test_legacy_article_without_operations_remains_supported(self):
        article = reviewed_article(); article.pop('operations')
        validate_article(article)

    def test_present_but_invalid_operations_cannot_fall_back_to_legacy(self):
        for value in (None,False,[],{},'passed',{'workflow_id':'fixture'}):
            article = reviewed_article(); article['operations'] = value
            with self.subTest(value=value), self.assertRaises(ContentValidationError):
                validate_article(article)

    def test_body_metadata_slug_faq_and_image_edits_invalidate_gate(self):
        edits = {'title':'다른 제목','description':'다른 설명','slug':'another-url','category':'another-category',
                 'heroImage':'/images/replaced.png','tags':['changed'],'faqs':[{'question':'질문','answer':'답변'}],
                 'markdown_content':'검토하지 않은 새 본문입니다.'}
        for field,value in edits.items():
            article = reviewed_article(); article[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ContentValidationError,'변경'):
                validate_article(article)

    def test_review_mutation_is_detected_even_when_article_is_unchanged(self):
        article = reviewed_article()
        article['operations']['review']['original_value'] = 'Changed review'
        with self.assertRaisesRegex(ContentValidationError,'보고서'):
            validate_article(article)

    def test_missing_failed_and_malformed_gate_fields_fail_closed(self):
        changes = [('status','pending'),('status',True),('article_hash',None),('article_hash','z'*64),
                   ('review_hash','0'*64),('checked_at',None),('checked_at','yesterday'),
                   ('checked_at','2026-09-18'),('evidence_ids',[]),('evidence_ids',['source-a','source-a']),
                   ('evidence_ids',[{}]),('evidence_ids',[''])]
        for field,value in changes:
            article=reviewed_article(); article['operations']['gate'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ContentValidationError):
                validate_article(article)
        for field in ('workflow_id','gate','review'):
            article=reviewed_article(); article['operations'].pop(field)
            with self.subTest(missing=field),self.assertRaises(ContentValidationError):
                validate_article(article)

    def test_review_claim_must_reference_gate_evidence_even_if_review_rehashed(self):
        article=reviewed_article(); article['operations']['review']['claims'][0]['source_id']='not-collected'
        rehash_review(article)
        with self.assertRaisesRegex(ContentValidationError,'출처'):
            validate_article(article)

    def test_claim_and_quote_shape_must_survive_rehash(self):
        changes=[('claim','not present in the article'),('claim','short'),('quote','short'),('assessment','unsupported')]
        for field,value in changes:
            article=reviewed_article(); article['operations']['review']['claims'][0][field]=value
            rehash_review(article)
            with self.subTest(field=field),self.assertRaises(ContentValidationError):
                validate_article(article)

    def test_review_conditions_cannot_be_overridden_by_hash_only(self):
        changes=[('decision','revise'),('rights','unclear'),('issues',['unresolved']),('claims',[]),
                 ('claims',[None]),('coverage_checked',1),('requires_expert_review',True),('original_value','')]
        for field,value in changes:
            article=reviewed_article(); article['operations']['review'][field]=value
            rehash_review(article)
            with self.subTest(field=field),self.assertRaises(ContentValidationError):
                validate_article(article)

    def test_valid_operations_allow_publisher_metadata_defaults_without_rehashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            publisher=GitHubPublisher({'github':{'repo_root':str(root),'blog_content_dir':str(root/'posts'),
                                                'auto_git_commit':False,'auto_git_push':False}})
            source=Path(publisher.publish_article(reviewed_article(),human_approved=True))
            metadata,body=publisher._read_post(source)
            self.assertIn('pubDate',metadata)
            self.assertEqual(metadata['title'],reviewed_article()['title'])
            self.assertNotIn('operations',metadata)
            self.assertIn('입력 파일의 형식을 먼저 확인합니다.',body)

    def test_gate_binds_thumbnail_bytes_and_requires_complete_asset_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=root/'blog-frontend/public/images/verified.png'
            image.parent.mkdir(parents=True);image.write_bytes(b'reviewed-image-bytes')
            article=reviewed_article()
            article['operations']['gate']['image_manifest']=[{'url':'/images/verified.png',
                'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]
            publisher=GitHubPublisher({'github':{'repo_root':str(root),'blog_content_dir':str(root/'posts'),
                                                'auto_git_commit':False,'auto_git_push':False}})
            image.write_bytes(b'replaced-after-review')
            with self.assertRaisesRegex(ContentValidationError,'SHA256'):
                publisher.publish_article(article,human_approved=True)
            self.assertFalse((root/'posts').exists())
            image.write_bytes(b'reviewed-image-bytes')
            article['operations']['gate']['image_manifest']=[]
            with self.assertRaisesRegex(ContentValidationError,'SHA256'):
                publisher.publish_article(article,human_approved=True)
            self.assertFalse((root/'posts').exists())
            article['operations']['gate']['image_manifest']=[{'url':'/images/verified.png',
                'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]
            self.assertTrue(Path(publisher.publish_article(article,human_approved=True)).exists())

    def test_malformed_or_duplicate_image_manifest_fails(self):
        for manifest in (None,{},[{}],[{'url':'https://other.invalid/image.png','sha256':'a'*64}],
                         [{'url':'/images/verified.png','sha256':'a'*64}]*2):
            article=reviewed_article();article['operations']['gate']['image_manifest']=manifest
            with self.subTest(manifest=manifest),self.assertRaises(ContentValidationError):
                validate_article(article)

    def test_stale_orchestrated_article_is_rejected_before_file_write(self):
        article=reviewed_article(); article['description']='Unreviewed edit'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            publisher=GitHubPublisher({'github':{'repo_root':str(root),'blog_content_dir':str(root/'posts'),
                                                'auto_git_commit':False,'auto_git_push':False}})
            with self.assertRaises(ContentValidationError):
                publisher.publish_article(article,human_approved=True)
            self.assertFalse((root/'posts').exists())


if __name__=='__main__':
    unittest.main()
