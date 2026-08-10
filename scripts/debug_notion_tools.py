"""API-post-page / API-update-page-markdown의 실제 입력 스키마와, 방금 만든
검증용 페이지에 마크다운을 다시 써봤을 때의 원본 응답을 확인하는 진단 스크립트.

verify_notion_write.py로 만든 페이지의 본문이 비어있는 문제를 진단하기 위한
스크립트 — API-update-page-markdown 호출 결과를 그냥 무시하지 않고 그대로 출력한다.

실행:
    python scripts/debug_notion_tools.py <page_id>

<page_id>를 안 주면 방금 verify_notion_write.py로 만든 페이지 ID를 기본값으로 쓴다.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mcp_client import NotionMCPClient  # noqa: E402

DEFAULT_PAGE_ID = "3b84bd0b-1658-81c2-ae92-f16fc835e5a7"


async def _try(session, label: str, args: dict) -> None:
    print(f"=== 시도: {label} ===")
    print("args:", args)
    result = await session.call_tool("API-update-page-markdown", args)
    print("isError:", getattr(result, "isError", None))
    print("content:", getattr(result, "content", None))
    print("structuredContent:", getattr(result, "structuredContent", None))
    print()


async def main() -> None:
    page_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PAGE_ID

    client = NotionMCPClient()
    async with client.session() as session:
        tools = await session.list_tools()
        for tool in tools.tools:
            if tool.name in ("API-update-page-markdown", "API-post-page"):
                print(f"=== {tool.name} inputSchema ===")
                print(tool.inputSchema)
                print()

        # 1) 문자열 shorthand (지금 notion_writer.py가 쓰는 방식 - 본문이 비었던 방식)
        await _try(
            session,
            "insert_content를 문자열로",
            {"page_id": page_id, "type": "insert_content", "insert_content": "## 문자열 방식 테스트\n\n내용입니다."},
        )

        # 2) 객체 형태 + position 명시
        await _try(
            session,
            "insert_content를 객체+position(end)으로",
            {
                "page_id": page_id,
                "type": "insert_content",
                "insert_content": {
                    "content": "## 객체+position 방식 테스트\n\n내용입니다.",
                    "position": {"type": "end"},
                },
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
