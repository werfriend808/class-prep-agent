# class-prep-agent — 실전 프로젝트 1: MCP 기반 Notion 페이지 검색 및 요약

자연어로 질의를 입력하면 Notion 팀스페이스에서 관련 수업 자료를 찾아 요약해주는 Streamlit 웹 서비스입니다. 멋사 NLP5기 "[AI 기반 교육활동 지원 서비스]" 프로젝트의 첫 단계(실전 프로젝트 1)이며, 전체 프로젝트 계획은 이 문서 맨 아래 "부록"에 정리되어 있습니다.

## 1. 무엇을 하는 서비스인가

검색창에 "토론 수업 관련 자료 찾아줘" 같은 자연어 질의를 입력하면:

1. 질의를 주제/키워드, 제목 정확 매칭, 속성 필터(학년·과목·날짜) 세 유형 중 하나로 분류하고
2. Notion MCP 서버를 통해 워크스페이스를 검색하거나 속성으로 필터링하고
3. 찾은 각 페이지의 본문을 조회해 Claude API로 요약한 뒤
4. 검색창 + 결과 카드 리스트(제목/태그/요약/Notion 링크) 형태로 보여줍니다.

## 2. 실행 방법

**사전 준비물**
- Python 3.10+
- Node.js / npx (`node -v`로 확인, LTS 권장) — Notion MCP 서버(`@notionhq/notion-mcp-server`)를 npx로 구동하기 위해 필요
- Notion Internal Integration 토큰 (https://www.notion.so/my-integrations 에서 발급, 검색 대상 페이지에 Connections로 연결까지 완료)
- Claude API 키 (https://console.anthropic.com 에서 발급, 계정에 크레딧 필요)

**설치 및 실행**

```bash
pip install -r requirements.txt
```

`.env.example`을 참고해 `.env`를 만들고 아래 값을 채웁니다.

```
NOTION_API_KEY=ntn_...                  # Notion Internal Integration 토큰
ANTHROPIC_API_KEY=sk-ant-...            # Claude API 키
NOTION_DATA_SOURCE_ID=...               # FILTER(학년/과목/날짜) 검색에 필요, 아래 3-2 참고
```

```bash
streamlit run app.py
```

**테스트 실행**

```bash
python -m pytest
```

네트워크나 API 키 없이도 통과하는 순수 로직 테스트(필터 변환, MCP 응답 파싱, 폴백 처리 등) 30개가 들어있습니다.

## 3. MCP 연동 방식

### 3-1. 전체 구조

```
사용자 질의
   │
   ▼
query_router.classify_query()  ──▶  질의 유형 판단 (TOPIC / TITLE / FILTER)
   │                                 + 학년/과목/날짜/학기 후보 추출 (정규식)
   ▼
mcp_client.NotionMCPClient       ──▶  npx로 notion-mcp-server 프로세스를 띄우고
   (stdio 기반 MCP 클라이언트)          stdio로 통신 (Model Context Protocol)
   │
   ▼
pipeline.search_and_summarize() ──▶  검색/필터 → 페이지 본문 조회 → Claude 요약
   │
   ▼
app.py (Streamlit)               ──▶  검색창 + 결과 카드 리스트 UI
```

- **MCP 서버**: 자체 구현 대신 Notion 공식 오픈소스 서버 [`@notionhq/notion-mcp-server`](https://github.com/makenotion/notion-mcp-server)를 `npx -y @notionhq/notion-mcp-server`로 그때그때 띄워서 씁니다. 인증은 `NOTION_TOKEN` 환경변수(Internal Integration 토큰)로 전달합니다.
- **MCP 클라이언트**: `src/mcp_client.py`의 `NotionMCPClient`가 공식 Python `mcp` SDK(`mcp.client.stdio.stdio_client` + `mcp.ClientSession`)로 위 프로세스와 stdio 연결을 맺고 `list_tools()` / `call_tool()`을 직접 호출합니다. 이 클라이언트를 직접 구현하는 것이 이번 프로젝트의 핵심 요구사항입니다.

### 3-2. 실제로 확인한 tool 이름과 스키마 (2026-07-27, 실 서버 실행 결과 기준)

`notion-mcp-server`의 README에는 `search`, `query-data-source`처럼 짧은 이름이 나오지만, 실제로 `list_tools()`를 호출해보면 OpenAPI operationId 그대로 `API-` 접두사가 붙어 있습니다.

```
API-post-search, API-query-data-source, API-retrieve-a-data-source,
API-retrieve-page-markdown, API-retrieve-a-database, API-retrieve-a-page, ...
```

이번 프로젝트에서 실제로 쓰는 tool은 세 가지입니다.

| Tool | 역할 | 사용 위치 |
|---|---|---|
| `API-post-search` | 주제/제목 검색 (`{"query": "..."}`) | TOPIC/TITLE 유형 |
| `API-query-data-source` | 속성(학년/과목/날짜/학기) 필터 검색 | FILTER 유형 |
| `API-retrieve-page-markdown` | 페이지 본문을 마크다운으로 조회 | 요약 입력 생성 |

`NOTION_DATA_SOURCE_ID`는 "수업 자료" 데이터소스의 ID로, `API-post-search` 응답의 `results[].parent.data_source_id` 값에서 확인할 수 있습니다 (`retrieve-a-database`로도 조회 가능).

**속성 스키마 (실제 응답으로 검증):** "학년"은 `select`, "다중 선택"(과목)은 `multi_select`, "날짜"는 `date`지만, **"학기"는 `select`처럼 보여도 실제로는 `rich_text`**입니다. `pipeline.build_notion_filter()`가 이 실제 타입 기준으로 Notion filter 객체를 만듭니다.

### 3-3. 검색 결과 후처리 (실사용 테스트로 발견한 이슈들)

Notion의 `search` API는 의미 기반 검색이 아니라 단순 텍스트 매칭에 가깝습니다. 실제로 붙여보면서 두 가지 문제를 발견하고 고쳤습니다.

1. **자연어 문장을 그대로 검색어로 넘기면 결과가 엉뚱하게 나옴.** "토론 수업 관련 자료 찾아줘"를 그대로 넘기면 제목과 거의 안 겹쳐서 무관한 페이지가 섞여 나왔습니다. → `query_router.clean_search_query()`가 "찾아줘"/"관련"/"자료" 같은 요청 표현을 제거하고 핵심 키워드("토론 수업")만 남겨서 검색합니다.
2. **Notion search가 단어 단위로 느슨하게 매칭함.** "학교생활 챗봇 만들기"로 검색해도 "생활"이나 "만들기"만 겹치는 무관한 페이지가 같이 반환됐습니다. → `pipeline._fetch_candidate_pages()`가 검색 결과 중 제목이 (구두점 차이만 무시하고) 검색어와 정확히 일치하는 페이지가 있으면 그 결과로 좁힙니다. 이 좁히기는 질의 유형 분류(TOPIC/TITLE) 결과와 무관하게 항상 적용되는데, LLM 분류가 실패했을 때 쓰는 규칙 기반 폴백이 문서유형 접미사(계획안/교안/퀴즈 등)가 없는 실제 제목을 TITLE이 아니라 TOPIC으로 잘못 분류하는 경우가 있었기 때문입니다.

### 3-4. 질의 유형 분류: LLM + 규칙 기반 하이브리드

`query_router.classify_query()`는 먼저 Claude API에 유형 판단을 맡기고, API 호출이 실패하면(키 없음, 크레딧 부족, 네트워크 오류 등) `_heuristic_classify()`로 자동 폴백합니다. 학년/과목/날짜/학기 속성 후보는 항상 정규식으로 먼저 뽑아두고, FILTER 유형일 때 이 값을 Notion filter 조건으로 변환합니다.

### 3-5. 요약 실패 시 폴백

Claude API 호출이 실패해도(크레딧 부족 등) 검색 자체는 확인할 수 있도록, `pipeline._summarize_or_fallback()`이 실패 시 AI 요약 대신 페이지 본문 앞부분을 그대로 보여줍니다.

## 4. 프로젝트 구조

```
app.py                   # Streamlit 진입점 (검색창 + 결과 카드 리스트)
src/
  config.py              # 환경변수 로딩
  mcp_client.py           # Notion MCP 클라이언트 (stdio, npx로 서버 구동)
  query_router.py         # 질의 유형 분류(TOPIC/TITLE/FILTER) + 검색어 정제
  pipeline.py             # 검색 → 조회 → 요약 오케스트레이션
  summarizer.py           # Claude API 요약
  llm.py                  # Claude API 클라이언트 공용 헬퍼
golden_set/queries.md     # 실제 샘플 데이터셋 기준 질의 유형별 테스트 케이스
tests/                    # 순수 로직 단위 테스트 (30개, 네트워크 불필요)
```

## 5. 알려진 제한사항

- Claude API 계정에 크레딧이 없으면 요약은 폴백(원문 일부)으로 표시됩니다. 정상적인 AI 요약을 보려면 https://platform.claude.com/settings/billing 에서 크레딧을 충전해야 합니다.
- `notion-mcp-server`는 호출마다 매번 새 프로세스를 띄우는 구조가 아니라 `NotionMCPClient.session()`으로 세션을 한 번 열어 여러 tool을 재사용하도록 되어 있지만, 검색 1건당 여전히 npx 프로세스 기동 비용이 있어 처음 실행 시 다소 느립니다.
- 과목 태그 표기가 데이터셋 내에서 일관되지 않습니다(예: "통합사회" vs "통합 사회1"). `golden_set/queries.md`의 "노이즈/예외 케이스"에 정리되어 있습니다.

---

## 부록: 전체 프로젝트 계획 (실전 1 · 실전 2 · 종합)

> 아래는 프로젝트 시작 시점에 정리해둔 전체 3단계 계획입니다. 실전 프로젝트 2와 종합 프로젝트를 시작할 때 참고용으로 남겨둡니다.

### A-1. 프로젝트 개요

생성형 AI를 활용해 교사의 수업 준비를 지원하는 서비스를 만드는 프로젝트입니다. 교사는 수업 하나를 준비하기 위해 수업계획안 작성, 교육과정 확인, 퀴즈·활동지 제작 등을 여러 도구를 오가며 반복 수행하는데, 이 과정을 생성형 AI와 외부 서비스(Notion, Google Docs, Google Forms 등) 연동으로 줄이는 것이 목표입니다.

핵심은 "AI API를 연결하는 것" 자체가 아니라, 사용자의 문제를 이해하고 이를 해결하는 워크플로우를 설계한 뒤 실제로 동작하는 서비스로 구현하는 경험입니다.

### A-2. 전체 구성: 3단계 파이프라인

| 단계 | 이름 | 핵심 기능 | MCP 활용 방향 | 대화 방식 |
|---|---|---|---|---|
| 1 | MCP 기반 Notion 페이지 검색 및 요약 | 자연어 질의 → Notion 검색 → 요약 | 읽기(Read) | 단발성 질의 (멀티턴 아님) |
| 2 | AI 챗봇 기반 수업계획안 생성 | 멀티턴 대화 → 토의·토론 수업계획안 생성 → NCIC 근거 제시 → Notion 페이지 생성 | 쓰기(Create) | 멀티턴 |
| 종합 | AI 기반 수업 활동 에이전트 서비스 | Activity별 AI Agent가 생성·수정까지 담당, 여러 외부 서비스 오케스트레이션 | 생성+수정, 여러 서비스 통합 | 멀티턴 + 후속 수정 요청 |

각 프로젝트는 독립적으로 수행 가능하지만, 실전 1(읽기/검색) → 실전 2(생성/쓰기) → 종합(생성+수정+멀티서비스 오케스트레이션) 순으로 역량이 쌓이도록 설계되어 있어, 이 순서대로 진행 중입니다.

### A-3. 실전 프로젝트 2 — AI 챗봇 기반 수업계획안 생성 (예정)

**개요:** 사용자와 멀티턴 대화를 통해 토의·토론 수업계획안을 완성하고, 국가교육과정(NCIC) 근거를 제시하며 Notion 페이지까지 생성하는 챗봇.

**필수 기능**
- 챗봇 인터페이스 + 멀티턴 대화
- 토의·토론 수업계획안 생성 (자료 개요, 수업 목표, 배경 읽기 자료, 핵심 개념, 토론 쟁점, 수업 흐름, 학생 활동지 예시, 평가 루브릭)
- NCIC 교육과정 근거 제시 (성취기준 코드, 관련 성취기준, 참고 원문/링크)
- Notion 페이지 생성 및 링크 반환
- 예외 상황 처리

**구현 조건:** Notion 페이지 생성은 MCP로, LLM으로 대화 관리 및 계획안 생성, 프론트엔드는 챗봇 UI 단일 화면.

**사전 조사 필요:** MCP를 통한 Notion 쓰기 방식, NCIC 자료 활용 방식(검색/RAG/벡터DB), 멀티턴 대화 상태 관리 방식.

### A-4. 종합 프로젝트 — AI 기반 수업 활동 에이전트 서비스 (예정)

**개요:** 교사의 수업 활동(토의·토론, 프로젝트 학습, 퀴즈)에 특화된 AI Agent를 설계하고, 여러 외부 서비스와 연동해 수업자료를 생성·수정하는 서비스. 핵심은 "Tool을 몇 개 연결했는가"가 아니라 "사용자에게 자연스러운 Workflow를 어떻게 설계했는가".

**Activity 3종 (최소 1개 이상 완성도 있게 구현 권장)**

| Activity | 생성/수정 대상 | 연동 서비스 | 예시 요청 |
|---|---|---|---|
| 토의·토론 | 수업계획안, 학생 활동지 | Notion, Google Docs | "고1 사회 토의 수업을 준비해줘." |
| 프로젝트(PBL) | 수업계획안, 학생 활동지 | Notion, Google Docs | "환경 문제 프로젝트 수업을 만들어줘." |
| Quiz | 퀴즈 문항 | Google Forms | "삼각형 단원 퀴즈를 만들어줘." |

**공통 요구사항:** 멀티턴 대화로 정보 수집 → NCIC 참고 생성 → 수정 요청 반영 → 외부 서비스에 반영 → 근거 제공.

**구현 조건:** AI Agent 설계(멀티턴, Activity별 Workflow, Tool Routing), NCIC 활용(검색/RAG/벡터DB 자유), 외부 서비스 연동은 MCP 우선 + 필요시 REST API 병행.

### A-5. 프로젝트 간 연계 흐름

```
실전 프로젝트 1              실전 프로젝트 2                종합 프로젝트
(Notion 검색/요약)     →     (Notion 생성 + NCIC 검증)  →   (다중 Agent + 생성/수정 오케스트레이션)
MCP 읽기(Read)               MCP 쓰기(Create)                MCP 읽기/쓰기/수정 + REST API 병행
단발 질의                     멀티턴 대화                      멀티턴 + 후속 수정 대화
Notion만 연동                 Notion만 연동                    Notion + Google Docs + Google Forms
```

### A-6. 참고자료

- MCP 공식 문서/스펙: https://modelcontextprotocol.io
- Notion MCP 서버(오픈소스): https://github.com/makenotion/notion-mcp-server
- Notion API 요청 제한: https://developers.notion.com/reference/request-limits
- NCIC 국가교육과정정보센터
- Claude API 요금: https://docs.claude.com/en/docs/about-claude/pricing

### A-7. 커스터마이징 결정 포인트 (실전 2·종합 진행 시 참고)

- **멀티턴 대화 방식:** UI 입력창 선구성+대화 조정 / 순차 질문 수집 / 초안 후 피드백 / 혼합 중 선택
- **NCIC 활용 방식:** 단순 검색 / RAG / 벡터DB 중 선택
- **Activity 선택 (종합):** 토의·토론 / PBL / Quiz 중 몇 개를 구현할지
- **외부 서비스 연동 방식:** MCP 전용 vs MCP+REST API 병행
- **선택 기능 채택 여부:** 생성 과정 시각화·이력 관리, Padlet 연동 등 추가 기능

---

*이 문서는 2026-07-27 기준으로 작성되었습니다. 실전 프로젝트 2, 종합 프로젝트 진행 상황에 따라 갱신이 필요합니다.*
