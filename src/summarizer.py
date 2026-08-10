"""검색된 페이지 본문을 LLM으로 요약한다.

`llm.complete()`를 통해 호출하므로 `.env`의 `LLM_PROVIDER` 설정(기본 Claude,
"clova"면 네이버 클로바 스튜디오)에 따라 실제 사용되는 provider가 바뀐다 —
자세한 내용은 llm.py 참고. 실전 1도 실전 2와 동일하게 provider-무관하게 만들어,
같은 클로바 키 하나로 프로젝트 전체를 크레딧 없이 검증할 수 있게 했다.
"""
from __future__ import annotations

from .llm import complete


def summarize_page(title: str, markdown_content: str, max_tokens: int = 300) -> str:
    """페이지 제목 + 마크다운 본문을 받아 한국어 3~4문장 요약을 반환한다."""
    prompt = (
        "다음은 교사가 Notion에 작성한 수업 자료 페이지입니다. "
        "핵심 내용을 3~4문장으로 한국어로 요약해주세요. "
        "수업 대상, 주제, 핵심 활동 위주로 요약하세요.\n\n"
        f"# {title}\n\n{markdown_content}"
    )
    return complete(prompt, max_tokens=max_tokens)
