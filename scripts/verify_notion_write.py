"""Notion 쓰기 연동(API-post-page / API-update-page-markdown) 수동 검증 스크립트.

Claude API를 거치지 않고 가짜 수업계획안 dict로 바로 notion_writer.save_lesson_plan_to_notion()
을 호출해본다. 크레딧 없이도 "MCP로 Notion 페이지를 실제로 생성할 수 있는가"만
따로 확인할 수 있다 (계획안 생성 자체는 아직 검증 못한 부분으로 남는다).

실행 전 준비:
    - .env에 NOTION_LESSON_PLAN_PARENT_ID가 설정되어 있어야 함
    - 그 페이지에 Integration이 Connections로 연결되어 있어야 함

실행:
    python scripts/verify_notion_write.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.notion_writer import save_lesson_plan_to_notion  # noqa: E402

FAKE_PLAN = {
    "subject": "사회",
    "grade": "고1",
    "topic": "[검증용] 환경 보전과 개발 중 무엇을 우선해야 하는가",
    "자료_개요": "이 계획안은 notion_writer.py의 Notion 쓰기 연동을 검증하기 위해 "
    "Claude API 없이 수동으로 만든 가짜 데이터입니다.",
    "수업_목표": "1. 환경 보전과 개발의 딜레마를 이해한다.\n2. 서로 다른 입장을 근거를 들어 주장할 수 있다.",
    "배경_읽기_자료": "예시 배경 자료 텍스트.",
    "핵심_개념": "지속가능발전, 생태시민",
    "토론_쟁점": "1. 개발이 우선인가, 보전이 우선인가?\n2. 지역 주민의 이익과 환경 보호는 양립 가능한가?",
    "수업_흐름": "1) 도입(5분): 사례 영상 시청\n2) 전개(30분): 모둠 토론\n3) 정리(10분): 발표 및 피드백",
    "학생_활동지_예시": "찬반 논거 정리표, 역할별 발언 카드",
    "평가_루브릭": "근거의 타당성(40%), 경청 태도(30%), 참여도(30%)",
    "ncic_references": [
        "[10통사1-01-01] 인간, 사회, 환경을 바라보는 시간적, 공간적, 사회적, 윤리적 "
        "관점의 의미와 특징을 사례를 통해 파악한다. (출처: [별책7] 사회과 교육과정.pdf)",
    ],
}


async def main() -> None:
    print("Notion 페이지 생성을 시도합니다...")
    result = await save_lesson_plan_to_notion(FAKE_PLAN)
    print("성공!")
    print("page_id:", result["page_id"])
    print("url:", result["url"])
    print("\n위 url을 열어서 제목/본문/NCIC 근거가 잘 들어갔는지 눈으로 확인해주세요.")


if __name__ == "__main__":
    asyncio.run(main())
