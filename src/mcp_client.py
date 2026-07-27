"""Notion MCP 서버(makenotion/notion-mcp-server)에 연결하는 MCP 클라이언트.

notion-mcp-server는 npx로 구동되는 별도 프로세스이며, 이 클래스는 stdio로
그 프로세스와 통신한다. 실전 프로젝트 1의 "MCP 클라이언트 직접 구현"
요구사항에 해당하는 부분.

사전 조건: Node.js / npx가 설치되어 있어야 하고, NOTION_API_KEY가 유효한
Internal Integration 토큰이어야 하며, 조회하려는 페이지/데이터베이스가
해당 Integration에 연결(Connections)되어 있어야 한다.

Tool 이름 확인 (2026-07-27, 실제 `list_tools()` 실행 결과):
    ['API-get-user', 'API-get-users', 'API-get-self', 'API-post-search',
     'API-get-block-children', 'API-patch-block-children', 'API-retrieve-a-block',
     'API-update-a-block', 'API-delete-a-block', 'API-retrieve-a-page',
     'API-patch-page', 'API-post-page', 'API-retrieve-a-page-property',
     'API-retrieve-a-comment', 'API-create-a-comment', 'API-query-data-source',
     'API-retrieve-a-data-source', 'API-update-a-data-source',
     'API-create-a-data-source', 'API-list-data-source-templates',
     'API-retrieve-a-database', 'API-move-page', 'API-retrieve-page-markdown',
     'API-update-page-markdown']

    README에 나온 "search", "query-data-source" 같은 짧은 이름이 아니라
    OpenAPI operationId 그대로 "API-" 접두사가 붙은 이름을 쓴다. 아래
    편의 메서드들은 이 실제 이름 기준으로 맞춰져 있다.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import NOTION_API_KEY


class NotionMCPClient:
    def __init__(self, notion_token: str = NOTION_API_KEY):
        self._server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env={"NOTION_TOKEN": notion_token},
        )

    @asynccontextmanager
    async def session(self):
        """MCP 세션을 연다 (notion-mcp-server 프로세스 1개를 새로 스폰).

        여러 tool을 한 번의 검색 흐름(검색 -> 여러 페이지 본문 조회)에서
        연달아 호출할 때는, 매번 call_tool()을 쓰기보다 이 컨텍스트
        매니저로 세션을 한 번만 열고 그 안에서 session.call_tool(...)을
        여러 번 호출하는 게 훨씬 빠르다 (프로세스 재기동 비용을 아낀다).

            async with client.session() as session:
                search_result = await session.call_tool("API-post-search", {"query": q})
                page_md = await session.call_tool("API-retrieve-page-markdown", {"page_id": pid})
        """
        async with stdio_client(self._server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[str]:
        """서버가 제공하는 tool 목록을 조회한다. (사전 조사/디버깅용)"""
        async with self.session() as session:
            result = await session.list_tools()
            return [tool.name for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """단발성 tool 호출. 세션을 매번 새로 열기 때문에, 한 번의 검색
        흐름에서 여러 tool을 연달아 호출해야 한다면 session()을 직접
        쓰는 게 낫다 (위 docstring 참고).

        자주 쓰게 될 실제 tool 이름 (list_tools()로 확인함):
          - "API-post-search": 페이지/데이터소스 검색 (질의 유형 1: 주제/키워드, 2: 제목)
          - "API-query-data-source": 속성(학년/과목/날짜) 필터 검색 (질의 유형 3)
          - "API-retrieve-a-data-source": 데이터소스 스키마 조회
          - "API-retrieve-page-markdown": 페이지 본문을 마크다운으로 조회 (요약 입력용)
        """
        async with self.session() as session:
            return await session.call_tool(name, arguments)

    async def search(self, query: str) -> Any:
        """주제/키워드/제목 검색 (POST /v1/search 래핑)."""
        return await self.call_tool("API-post-search", {"query": query})

    async def query_data_source(self, data_source_id: str, filter_: dict[str, Any] | None = None) -> Any:
        """학년/과목/날짜 속성 필터 검색."""
        args: dict[str, Any] = {"data_source_id": data_source_id}
        if filter_:
            args["filter"] = filter_
        return await self.call_tool("API-query-data-source", args)

    async def get_page_markdown(self, page_id: str) -> Any:
        """페이지 본문을 마크다운으로 조회 (요약 파이프라인 입력)."""
        return await self.call_tool("API-retrieve-page-markdown", {"page_id": page_id})

    async def retrieve_data_source(self, data_source_id: str) -> Any:
        """데이터소스 스키마 조회 (속성 이름/타입 확인용, 디버깅에 유용)."""
        return await self.call_tool("API-retrieve-a-data-source", {"data_source_id": data_source_id})

    async def retrieve_database(self, database_id: str) -> Any:
        """데이터베이스 메타데이터 조회 (data_source_id 목록을 얻을 때 사용)."""
        return await self.call_tool("API-retrieve-a-database", {"database_id": database_id})
