"""Agent and Scheduler Management Module for Systemd Timers & Services."""
import re
import logging
import subprocess
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Registered automation agents and schedulers on Raspberry Pi 5
SYSTEM_AGENTS = {
    "absian": {
        "name": "앱시안 자동 포스팅",
        "icon": "🤖",
        "timer": "auto-blog.timer",
        "service": "auto-blog.service",
        "desc": "AI/테크 글 초안 작성 & 검토 큐 적재 (11:10, 18:30 + 가변 지연)"
    },
    "goldenlife": {
        "name": "골든라이프 자동 포스팅",
        "icon": "👵",
        "timer": "auto-blog-goldenlife-pipeline.timer",
        "service": "auto-blog-goldenlife-pipeline.service",
        "desc": "시니어/연금 글 초안 작성 & 검토 큐 적재 (09:20, 15:40 + 가변 지연)"
    },
    "kpop": {
        "name": "K-Pop 한글 학습 포스팅",
        "icon": "🎵",
        "timer": "auto-blog-kpop-pipeline.timer",
        "service": "auto-blog-kpop-pipeline.service",
        "desc": "K-Pop 한글 학습 초안 작성 & 검토 큐 적재 (13:15 + 가변 지연)"
    },
    "dryrun": {
        "name": "모의점검 및 이상탐지",
        "icon": "🩺",
        "timer": "auto-blog-dryrun.timer",
        "service": "auto-blog-dryrun.service",
        "desc": "일일 파이프라인 무결성 점검 및 이상 탐지 (06:30 + 가변 지연)"
    },
    "morning": {
        "name": "아침 현황 브리핑",
        "icon": "🌅",
        "timer": "auto-blog-morning.timer",
        "service": "auto-blog-morning.service",
        "desc": "매일 08:00 사이트 운영 현황 텔레그램 브리핑"
    },
    "evening": {
        "name": "저녁 트래픽/수익 리포트",
        "icon": "🌆",
        "timer": "auto-blog-evening.timer",
        "service": "auto-blog-evening.service",
        "desc": "매일 19:00 일일 실측 클릭 & 뷰 트래픽 보고서"
    },
    "health": {
        "name": "라즈베리파이 시스템 헬스",
        "icon": "🍓",
        "timer": "auto-blog-health.timer",
        "service": "auto-blog-health.service",
        "desc": "매일 12:00 CPU 온도, NVMe 디스크 모니터링 알림"
    },
    "geeknews": {
        "name": "GeekNews 주간 브리핑",
        "icon": "📰",
        "timer": "auto-blog-geeknews.timer",
        "service": "auto-blog-geeknews.service",
        "desc": "매주 금요일 08:00 긱뉴스 인기 토픽 심층 기획 포스팅"
    },
    "report": {
        "name": "주간 종합 성과 리포트",
        "icon": "📊",
        "timer": "auto-blog-report.timer",
        "service": "auto-blog-report.service",
        "desc": "매주 일요일 20:00 주간 조회수 및 성과 분석 리포트"
    }
}

class AgentManager:
    """Manages systemd user timers and background automation pipeline services."""

    def __init__(self):
        self.agents = SYSTEM_AGENTS

    def _run_systemctl(self, *args) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["systemctl", "--user", *args],
                capture_output=True,
                text=True,
                timeout=12
            )
        except Exception as e:
            logger.error(f"systemctl 실행 실패 ({args}): {e}")
            raise

    def get_timer_info_map(self) -> Dict[str, Dict[str, str]]:
        """Parses `systemctl --user list-timers --all` output."""
        timer_info = {}
        try:
            res = self._run_systemctl("list-timers", "--all", "--no-pager", "--full")
            lines = res.stdout.strip().split("\n")
            if len(lines) > 1:
                # Skip header
                for line in lines[1:]:
                    parts = line.split()
                    if not parts or parts[0] == "":
                        continue
                    # Match timer name ending with .timer
                    for p in parts:
                        if p.endswith(".timer"):
                            timer_name = p
                            timer_info[timer_name] = line
                            break
        except Exception as e:
            logger.warning(f"list-timers 파싱 실패: {e}")
        return timer_info

    def get_agent_status(self, key: str) -> Optional[Dict[str, Any]]:
        agent = self.agents.get(key)
        if not agent:
            return None

        timer_unit = agent["timer"]
        service_unit = agent["service"]

        # Check timer status
        res_timer = self._run_systemctl("is-active", timer_unit)
        timer_active = (res_timer.stdout.strip() == "active")

        # Check service status (is currently running)
        res_svc = self._run_systemctl("is-active", service_unit)
        service_active = (res_svc.stdout.strip() == "active")

        # Parse schedule & next run
        timer_line = ""
        res_timers = self._run_systemctl("list-timers", timer_unit, "--no-pager", "--full")
        next_run = "스케줄 확인 대기"
        left_time = ""
        last_run = ""
        
        lines = res_timers.stdout.strip().split("\n")
        if len(lines) > 1:
            for l in lines[1:]:
                if timer_unit in l:
                    timer_line = l
                    break

        if timer_line:
            # Format: NEXT LEFT LAST PASSED UNIT ACTIVATES
            # Example: Mon 2026-09-14 00:00:00 KST 3h 30min left Sun 2026-09-13 20:00:10 KST 20min ago
            # Extract left time (e.g. 3h 30min left, 11h left)
            left_match = re.search(r"(\d+(?:[a-z]+|\s*[a-z]+)+\s+left)", timer_line, re.IGNORECASE)
            if left_match:
                left_time = left_match.group(1)

            date_match = re.search(r"(\w+\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", timer_line)
            if date_match:
                next_run = date_match.group(1)

        return {
            "key": key,
            "name": agent["name"],
            "icon": agent["icon"],
            "desc": agent["desc"],
            "timer": timer_unit,
            "service": service_unit,
            "timer_active": timer_active,
            "service_active": service_active,
            "next_run": next_run,
            "left_time": left_time,
            "timer_line": timer_line
        }

    def list_all_agents(self) -> List[Dict[str, Any]]:
        results = []
        for key in self.agents.keys():
            st = self.get_agent_status(key)
            if st:
                results.append(st)
        return results

    def start_agent(self, key: str) -> (bool, str):
        agent = self.agents.get(key)
        if not agent:
            return False, f"알 수 없는 에이전트 키: {key}"
        res = self._run_systemctl("start", agent["timer"])
        if res.returncode == 0:
            return True, f"✅ <b>{agent['icon']} {agent['name']}</b> 타이머가 <b>시작(활성화)</b>되었습니다."
        return False, f"❌ 타이머 시작 실패: {res.stderr or res.stdout}"

    def stop_agent(self, key: str) -> (bool, str):
        agent = self.agents.get(key)
        if not agent:
            return False, f"알 수 없는 에이전트 키: {key}"
        res = self._run_systemctl("stop", agent["timer"])
        if res.returncode == 0:
            return True, f"⏸️ <b>{agent['icon']} {agent['name']}</b> 타이머가 <b>일시중지</b>되었습니다."
        return False, f"❌ 타이머 중지 실패: {res.stderr or res.stdout}"

    def restart_agent(self, key: str) -> (bool, str):
        agent = self.agents.get(key)
        if not agent:
            return False, f"알 수 없는 에이전트 키: {key}"
        res = self._run_systemctl("restart", agent["timer"])
        if res.returncode == 0:
            return True, f"🔄 <b>{agent['icon']} {agent['name']}</b> 타이머가 <b>재시작</b>되었습니다."
        return False, f"❌ 타이머 재시작 실패: {res.stderr or res.stdout}"

    def trigger_run_now(self, key: str) -> (bool, str):
        agent = self.agents.get(key)
        if not agent:
            return False, f"알 수 없는 에이전트 키: {key}"
        # Trigger background service immediately
        res = self._run_systemctl("start", agent["service"])
        if res.returncode == 0:
            return True, f"🚀 <b>{agent['icon']} {agent['name']}</b> 파이프라인이 <b>지금 즉시 백그라운드에서 실행</b>되었습니다!"
        return False, f"❌ 즉시 실행 실패: {res.stderr or res.stdout}"
