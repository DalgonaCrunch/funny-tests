#!/usr/bin/env python3
"""
AI 협업 개발 시스템
아키텍트(PM/QA/테스터)와 개발자가 Claude Code CLI를 통해 협업합니다.
결과는 텔레그램으로 실시간 전송됩니다.

사용법: python3 bot_collab.py "개발할 내용을 여기에 입력"
"""

import subprocess
import sys
import time
import os
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# === 설정 ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, ".token")
WORK_DIR = os.path.join(SCRIPT_DIR, "workspace")
CHAT_ID = "7848325545"
MAX_TURNS = 10
DELAY = 3  # 턴 사이 대기 시간(초)
MODEL = "sonnet"  # sonnet이 빠르고 경제적, opus로 변경 가능

# === 시스템 프롬프트 ===
ARCHITECT_SYSTEM = """당신은 시니어 소프트웨어 아키텍트이자 PM/QA/테스터입니다.

역할:
- 사용자의 요구사항을 분석하고 기술 설계를 수행
- 개발자에게 한 번에 하나의 구체적이고 명확한 작업을 지시
- 개발자의 작업 결과를 리뷰하고 품질 검증
- 버그나 개선점이 있으면 수정 지시
- 모든 작업이 만족스럽게 완료되면 [DONE]을 응답에 포함

규칙:
- 한국어로 소통
- 응답은 500자 이내로 간결하게
- 한 번에 하나의 작업만 지시
- 직접 코드를 작성하지 말고 개발자에게 지시
- 파일 구조, 기술 스택, 구현 방향을 명확히 제시"""

DEVELOPER_SYSTEM = """당신은 시니어 풀스택 개발자입니다.

역할:
- 아키텍트의 지시에 따라 실제 코드를 작성하고 파일을 생성/수정
- Write, Edit, Bash 등 도구를 활용하여 실제 파일을 만듦
- 작업 완료 후 무엇을 했는지 간결히 보고

규칙:
- 한국어로 소통
- 응답은 500자 이내로 간결하게
- 반드시 실제로 파일을 생성/수정할 것
- 작업 후 생성/수정한 파일 목록과 핵심 내용을 보고"""


def load_token():
    """텔레그램 봇 토큰 로드"""
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def send_telegram(text, token):
    """텔레그램으로 메시지 전송"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if len(text) > 4000:
        text = text[:4000] + "\n...(잘림)"
    data = urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        urlopen(Request(url, data=data), timeout=10)
    except Exception as e:
        print(f"[텔레그램 전송 실패] {e}")


def run_claude(system_prompt, message, use_tools=False):
    """Claude Code CLI를 print 모드로 실행"""
    cmd = [
        "claude", "-p",
        "--model", MODEL,
        "--system-prompt", system_prompt,
    ]

    if use_tools:
        cmd.append("--dangerously-skip-permissions")
        cmd.extend(["--allowed-tools",
                     "Read", "Write", "Edit", "Bash", "Glob", "Grep"])

    cmd.append(message)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=WORK_DIR,
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            output = f"(에러: {result.stderr[:300]})"
        return output or "(응답 없음)"
    except subprocess.TimeoutExpired:
        return "(시간 초과 - 180초)"
    except Exception as e:
        return f"(실행 오류: {e})"


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 bot_collab.py '개발할 내용'")
        sys.exit(1)

    token = load_token()
    task = " ".join(sys.argv[1:])

    # 작업 디렉토리 확인
    os.makedirs(WORK_DIR, exist_ok=True)

    send_telegram(
        f"🚀 AI 협업 개발 시작!\n"
        f"\n📋 태스크: {task}"
        f"\n📁 작업 디렉토리: workspace/"
        f"\n🔄 최대 {MAX_TURNS}턴"
        f"\n\n👔 아키텍트 + 💻 개발자 협업 모드",
        token,
    )

    history = []
    final_turn = MAX_TURNS

    for turn in range(1, MAX_TURNS + 1):
        # ========== 아키텍트 턴 ==========
        if turn == 1:
            arch_input = (
                f"사용자 요구사항:\n{task}\n\n"
                f"작업 디렉토리: {WORK_DIR}\n\n"
                f"분석 후 개발자에게 첫 번째 작업을 지시해주세요."
            )
        else:
            recent = "\n\n".join(history[-4:])
            arch_input = (
                f"사용자 요구사항: {task}\n\n"
                f"최근 대화:\n{recent}\n\n"
                f"개발자의 보고를 검토하고 다음 지시를 내려주세요. "
                f"모든 작업이 완료되었으면 [DONE]을 포함하세요."
            )

        print(f"\n{'='*40}")
        print(f"[턴 {turn}/{MAX_TURNS}] 👔 아키텍트 실행 중...")
        arch_resp = run_claude(ARCHITECT_SYSTEM, arch_input, use_tools=False)
        history.append(f"[아키텍트]: {arch_resp}")
        send_telegram(f"👔 아키텍트 (턴 {turn}/{MAX_TURNS}):\n\n{arch_resp}", token)
        print(f"아키텍트 응답 완료 ({len(arch_resp)}자)")

        if "[DONE]" in arch_resp:
            send_telegram("✅ 아키텍트가 모든 작업 완료를 확인했습니다!", token)
            final_turn = turn
            break

        time.sleep(DELAY)

        # ========== 개발자 턴 ==========
        recent = "\n\n".join(history[-4:])
        dev_input = (
            f"프로젝트 목표: {task}\n\n"
            f"최근 대화:\n{recent}\n\n"
            f"아키텍트의 최신 지시에 따라 작업을 수행하고 결과를 보고해주세요."
        )

        print(f"[턴 {turn}/{MAX_TURNS}] 💻 개발자 실행 중...")
        dev_resp = run_claude(DEVELOPER_SYSTEM, dev_input, use_tools=True)
        history.append(f"[개발자]: {dev_resp}")
        send_telegram(f"💻 개발자 (턴 {turn}/{MAX_TURNS}):\n\n{dev_resp}", token)
        print(f"개발자 응답 완료 ({len(dev_resp)}자)")

        time.sleep(DELAY)
        final_turn = turn
    else:
        send_telegram(
            f"⏰ 최대 턴({MAX_TURNS})에 도달하여 세션을 종료합니다.", token
        )

    # 최종 결과 보고
    send_telegram(
        f"🏁 AI 협업 개발 세션 종료!\n"
        f"📊 총 {final_turn}턴 진행\n"
        f"📁 결과물: workspace/ 디렉토리 확인",
        token,
    )
    print(f"\n세션 종료. 총 {final_turn}턴 진행.")


if __name__ == "__main__":
    main()
