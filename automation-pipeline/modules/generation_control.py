"""Prevent retired timers/manual legacy paths from spending model calls."""
def legacy_generation_allowed(config):
    if config.get("operations", {}).get("legacy_generation_enabled", True) is False:
        print("기존 자동 생성은 중지되었습니다. blog-operations/manage.py --help의 팀 작업 흐름을 사용하세요.")
        return False
    return True
