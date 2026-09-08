import os
import json
import shutil
import subprocess
from typing import Dict, Any, Optional

class AntigravityRunner:
    """
    Google Antigravity CLI (`agy`) 및 Python SDK, 온디바이스 로컬 모델을 통합 실행하는 러너
    라즈베리파이 환경에서 별도의 API 키 없이 Antigravity 인증 세션 또는 로컬 엔진을 활용
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.engine_cfg = config.get("engine", {})
        self.provider = self.engine_cfg.get("provider", "antigravity_cli")
        self.cli_cmd = self.engine_cfg.get("cli_command", "agy")
        self.local_model = self.engine_cfg.get("local_model", "gemma2:2b")
        self.ollama_url = self.engine_cfg.get("ollama_url", "http://localhost:11434/v1")

    def get_cli_path(self) -> Optional[str]:
        """agy 또는 antigravity CLI 실행 파일 경로 탐색"""
        candidates = [
            shutil.which(self.cli_cmd),
            shutil.which("agy"),
            shutil.which("antigravity"),
            os.path.expanduser("~/.local/bin/agy"),
            os.path.expanduser("~/.local/bin/antigravity"),
            "/home/ian/.local/bin/agy",
            "/home/ian/Antigravity-arm64/antigravity",
            "/usr/local/bin/agy",
            "/usr/bin/agy"
        ]
        for path in candidates:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path
        return None

    def is_cli_available(self) -> bool:
        return self.get_cli_path() is not None

    def generate_text(self, system_prompt: str, user_prompt: str, model_name: Optional[str] = None, effort: Optional[str] = None) -> Optional[str]:
        """
        Antigravity CLI 또는 SDK, 로컬 엔진을 통해 텍스트 생성 수행
        """
        # 1. Antigravity CLI (`agy`) 실행 시도
        cli_path = self.get_cli_path()
        if cli_path:
            try:
                full_prompt = f"{system_prompt}\n\n[USER REQUEST]\n{user_prompt}"
                
                cmd = [cli_path, "--dangerously-skip-permissions"]
                mapped_model = model_name
                mapped_effort = effort
                if model_name:
                    if "gemini-3.1-pro" in model_name:
                        mapped_model = "gemini-3.1-pro-high" if effort != "low" else "gemini-3.1-pro-low"
                        mapped_effort = None
                    elif "flash" in model_name:
                        mapped_model = "gemini-3.8-flash-high"
                        mapped_effort = None

                if mapped_model:
                    cmd.extend(["--model", mapped_model])
                if mapped_effort:
                    cmd.extend(["--effort", mapped_effort])
                cmd.extend(["-p", full_prompt])

                print(f"🤖 Antigravity CLI 호출 중... (모델: {mapped_model or 'default'}, 추론: {mapped_effort or 'default'})")
                env = os.environ.copy()
                env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                else:
                    if model_name or effort:
                        print(f"⚠️ [AntigravityRunner] CLI 플래그 오류 ({result.stderr.strip()[:100]}). 기본 옵션으로 재시도...")
                        res_fallback = subprocess.run(
                            [cli_path, "--dangerously-skip-permissions", "-p", full_prompt],
                            capture_output=True,
                            text=True,
                            timeout=240,
                            env=env
                        )
                        if res_fallback.returncode == 0 and res_fallback.stdout.strip():
                            return res_fallback.stdout.strip()
                    print(f"[AntigravityRunner] CLI 반환 에러 code={result.returncode}: {result.stderr}")
            except Exception as e:
                print(f"[AntigravityRunner] CLI 실행 예외: {e}")

        # 2. Antigravity Python SDK (`google-antigravity`) 시도
        try:
            import asyncio
            from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

            async def _run_sdk():
                agent_config = LocalAgentConfig(
                    system_instructions=system_prompt,
                    capabilities=CapabilitiesConfig()
                )
                async with Agent(agent_config) as agent:
                    resp = await agent.chat(user_prompt)
                    output_tokens = []
                    async for token in resp:
                        output_tokens.append(token)
                    return "".join(output_tokens)

            print("🤖 Antigravity Python SDK Agent를 통해 콘텐츠 생성 중...")
            sdk_result = asyncio.run(_run_sdk())
            if sdk_result and sdk_result.strip():
                return sdk_result.strip()
        except ImportError:
            pass
        except Exception as e:
            print(f"[AntigravityRunner] SDK 실행 예외: {e}")

        # 3. 라즈베리파이 5 로컬 온디바이스 엔진 (Ollama / Gemma) 시도
        try:
            import requests
            ollama_endpoint = f"{self.ollama_url.rstrip('/')}/chat/completions"
            payload = {
                "model": self.local_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7
            }
            res = requests.post(ollama_endpoint, json=payload, timeout=90)
            if res.status_code == 200:
                data = res.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content:
                    print(f"🍓 라즈베리파이 5 로컬 모델 ({self.local_model})로 생성 완료!")
                    return content
        except Exception:
            pass

        return None
