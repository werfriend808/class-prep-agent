"""활동지 생성 실패("LLM 응답을 활동지 형식으로 해석하지 못했어요") 원인 진단용.

WorksheetError가 나면 JSON 파싱이 실패했다는 것만 알 수 있고 이유(JSON이
아예 아닌지, 설명 텍스트가 앞뒤에 붙었는지, max_tokens 부족으로 중간에
잘렸는지 등)는 알 수 없다. 이 스크립트는 실제로 LLM이 뭘 돌려주는지
raw 텍스트 그대로 출력해서 원인을 눈으로 보게 해준다.

실행:
    python scripts/debug_worksheet_generation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import LLM_PROVIDER  # noqa: E402
from src.llm import complete  # noqa: E402
from src.worksheet import _build_prompt  # noqa: E402

FAKE_PLAN = {
    "subject": "사회",
    "grade": "고1",
    "topic": "환경 보전과 개발 중 무엇을 우선해야 하는가",
    "토론_쟁점": "개발과 보전 중 우선순위",
    "수업_흐름": "도입-전개-정리",
}


def main() -> None:
    print(f"LLM_PROVIDER = {LLM_PROVIDER!r}\n")
    prompt = _build_prompt(FAKE_PLAN, revision_request="활동지 난이도를 낮춰줘")

    raw = complete(prompt, max_tokens=1500)
    print(f"--- raw response (길이: {len(raw)}자) ---")
    print(raw)
    print("--- raw response 끝 ---\n")

    if not raw.strip().startswith("{") and not raw.strip().startswith("```"):
        print("[진단] 응답이 '{'나 '```'로 시작하지 않음 — JSON 앞에 설명 텍스트가 붙었을 가능성.")
    if not raw.rstrip().endswith("}") and not raw.rstrip().endswith("```"):
        print("[진단] 응답이 '}'나 '```'로 끝나지 않음 — max_tokens(1500)에 걸려 중간에 잘렸을 가능성.")


if __name__ == "__main__":
    main()
