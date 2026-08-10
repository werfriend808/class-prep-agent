"""실제 LLM 호출로 수업계획안 생성을 검증하는 스크립트.

.env의 LLM_PROVIDER 설정(anthropic 또는 clova)에 따라 실제로 사용되는
provider가 달라진다. Notion에는 저장하지 않고 생성 결과만 출력한다 —
Notion 쓰기는 scripts/verify_notion_write.py로 이미 따로 검증했다.

실행:
    python scripts/verify_lesson_plan_generation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import LLM_PROVIDER  # noqa: E402
from src.lesson_plan import LessonPlanError, generate_lesson_plan  # noqa: E402


def main() -> None:
    print(f"LLM_PROVIDER = {LLM_PROVIDER!r}")
    print("수업계획안 생성을 시도합니다...\n")

    try:
        plan = generate_lesson_plan(
            subject="사회",
            topic="환경 보전과 개발 중 무엇을 우선해야 하는가",
            grade="고1",
        )
    except LessonPlanError as e:
        print("실패:", e)
        return

    for key, value in plan.items():
        print(f"--- {key} ---")
        if isinstance(value, list):
            for item in value:
                print(f"  - {item}")
        else:
            print(value)
        print()


if __name__ == "__main__":
    main()
