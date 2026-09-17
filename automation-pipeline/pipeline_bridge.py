"""Process boundary for cross-site actions; avoids Python module-cache collisions."""
import contextlib
import json
import sys
from daily_kpop_pipeline import load_config, publish_queued_draft
from modules.draft_queue import DraftApprovalQueue
from modules.gpt_images import prepare_article_images
from integrations.telegram_bot import TelegramNotifier, _load_env_file

def main():
    payload = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        _load_env_file()
        config = load_config()
        action = sys.argv[1]
        if action == "publish":
            success, result = publish_queued_draft(config, payload["draft_id"], human_approved=True)
            output = {"success": success, "result": result}
        elif action == "images":
            output = prepare_article_images(payload, config)
        elif action == "review":
            draft = DraftApprovalQueue().get_draft(payload["draft_id"])
            if not draft:
                raise ValueError("Unknown draft")
            TelegramNotifier(config).send_review_report(draft["draft_id"], draft["article"], draft["review"])
            output = {"success": True}
        else:
            raise ValueError("Unknown action")
    print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    main()
