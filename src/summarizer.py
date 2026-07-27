"""검색된 페이지 본문을 Claude API로 요약한다."""
from __future__ import annotations

from .config import SUMMARY_MODEL
from .llm import get_client


def summarize_page(title: str, markdown_content: str, max_tokens: int = 300) -> str:
    """페이지 제목 + 마크다운 본문을 받아 한국어 3~4문장 요약을 반환한다."""
    client = get_client()
    message = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": (
                    "다음은 교사가 Notion에 작성한 수업 자료 페이지입니다. "
                    "핵심 내용을 3~4문장으로 한국어로 요약해주세요. "
                    "수업 대상, 주제, 핵심 활동 위주로 요약하세요.\n\n"
                    f"# {title}\n\n{markdown_content}"
                ),
            }
        ],
    )
    return message.content[0].text
