# class-prep-agent — 멋사 NLP5기 "AI 기반 교육활동 지원 서비스" (실전 1·2 + 종합 프로젝트)

멋사 NLP5기 "[AI 기반 교육활동 지원 서비스]" 프로젝트의 구현체입니다. 하나의 저장소에서 두 개의 Streamlit 앱으로 제공합니다.

- **실전 프로젝트 1** (`app.py`): 자연어 질의로 Notion 팀스페이스의 수업 자료를 검색·요약
- **실전 프로젝트 2 + 종합 프로젝트** (`chat_app.py`): 화면 상단 Activity 선택(토의·토론 / Quiz)으로 시작해서, 멀티턴 챗봇으로 토의·토론 수업계획안을 생성해 Notion에 저장하고(실전 2) 학생 활동지(Google Docs)까지 만드는 흐름과, 퀴즈 문항을 생성해 Google Forms에 자동 반영하는 흐름을 하나의 앱에서 고를 수 있습니다(종합 프로젝트). 두 Activity 모두 생성 후 채팅으로 계속 수정을 요청하면 이미 만들어진 외부 문서에 자동으로 반영됩니다. 실전 2를 별도 앱으로 분리하지 않고 같은 파일 위에서 확장한 이유는 아래 13번 참고, Quiz Activity를 같은 앱에 통합한 이유는 16번 참고.

전체 프로젝트 계획은 이 문서 맨 아래 "부록"에 정리되어 있습니다.

---

# 실전 프로젝트 1: MCP 기반 Notion 페이지 검색 및 요약

## 1. 무엇을 하는 서비스인가

검색창에 "토론 수업 관련 자료 찾아줘" 같은 자연어 질의를 입력하면:

1. 질의를 주제/키워드, 제목 정확 매칭, 속성 필터(학년·과목·날짜) 세 유형 중 하나로 분류하고
2. Notion MCP 서버를 통해 워크스페이스를 검색하거나 속성으로 필터링하고
3. 찾은 각 페이지의 본문을 조회해 LLM(Claude 또는 네이버 클로바)으로 요약한 뒤
4. 검색창 + 결과 카드 리스트(제목/태그/요약/Notion 링크) 형태로 보여줍니다.

## 2. 실행 방법

**사전 준비물**
- Python 3.10+
- Node.js / npx (`node -v`로 확인, LTS 권장) — Notion MCP 서버(`@notionhq/notion-mcp-server`)를 npx로 구동하기 위해 필요
- Notion Internal Integration 토큰 (https://www.notion.so/my-integrations 에서 발급, 검색 대상 페이지에 Connections로 연결까지 완료)
- 요약/질의분류/계획안 생성에 쓸 LLM 키 하나: `ANTHROPIC_API_KEY`(Claude, https://console.anthropic.com 에서 발급, 계정에 크레딧 필요) 또는 `LLM_PROVIDER=clova` + `HCX_API_KEY`(네이버 클로바 스튜디오) — 아래 8-5 참고. 둘 다 없어도 앱은 실행되고, 요약/분류/계획안 생성만 규칙 기반 폴백 또는 오류 메시지로 대체됩니다.

**설치 및 실행**

```bash
pip install -r requirements.txt
```

`.env.example`을 참고해 `.env`를 만들고 아래 값을 채웁니다.

```
NOTION_API_KEY=ntn_...                  # Notion Internal Integration 토큰
ANTHROPIC_API_KEY=sk-ant-...            # Claude API 키 (LLM_PROVIDER=clova면 대신 HCX_API_KEY 사용)
NOTION_DATA_SOURCE_ID=...               # FILTER(학년/과목/날짜) 검색에 필요, 아래 3-2 참고
```

```bash
streamlit run app.py
```

**테스트 실행**

```bash
python -m pytest
```

`tests/`에는 실전 1·2 테스트가 함께 들어있어 `python -m pytest` 한 번으로 전부(현재 76개) 실행됩니다. 네트워크나 API 키 없이도 통과하는 순수 로직 테스트(필터 변환, MCP 응답 파싱, 폴백 처리, 대화 상태 전이 등)로만 구성되어 있습니다.

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
pipeline.search_and_summarize() ──▶  검색/필터 → 페이지 본문 조회 → LLM 요약
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

`query_router.classify_query()`는 먼저 LLM(`llm.complete()`, provider는 `.env`의 `LLM_PROVIDER`를 따름)에 유형 판단을 맡기고, 호출이 실패하면(키 없음, 크레딧 부족, 네트워크 오류 등) `_heuristic_classify()`로 자동 폴백합니다. 학년/과목/날짜/학기 속성 후보는 항상 정규식으로 먼저 뽑아두고, FILTER 유형일 때 이 값을 Notion filter 조건으로 변환합니다.

### 3-5. 요약 실패 시 폴백

LLM 호출이 실패해도(크레딧 부족 등) 검색 자체는 확인할 수 있도록, `pipeline._summarize_or_fallback()`이 실패 시 AI 요약 대신 페이지 본문 앞부분을 그대로 보여줍니다.

## 4. 프로젝트 구조

```
app.py                   # Streamlit 진입점 (검색창 + 결과 카드 리스트)
src/
  config.py              # 환경변수 로딩
  mcp_client.py           # Notion MCP 클라이언트 (stdio, npx로 서버 구동)
  query_router.py         # 질의 유형 분류(TOPIC/TITLE/FILTER) + 검색어 정제
  pipeline.py             # 검색 → 조회 → 요약 오케스트레이션
  summarizer.py           # LLM 요약 (llm.complete() 사용)
  llm.py                  # Claude/클로바 공용 LLM 호출 어댑터 (complete())
golden_set/queries.md     # 실제 샘플 데이터셋 기준 질의 유형별 테스트 케이스
tests/                    # 실전 1 관련 순수 로직 단위 테스트 (실전 2 테스트는 9번 참고, 합쳐서 python -m pytest 한 번에 실행)
```

## 5. 알려진 제한사항

- 사용 중인 LLM provider(Claude 또는 클로바)에 크레딧/사용량이 없으면 요약은 폴백(원문 일부)으로 표시됩니다. Claude를 쓰려면 https://platform.claude.com/settings/billing 에서 크레딧을 충전하거나, `.env`에서 `LLM_PROVIDER=clova`로 전환해 네이버 클로바 스튜디오 키를 쓸 수 있습니다 (아래 8-5 참고).
- `notion-mcp-server`는 호출마다 매번 새 프로세스를 띄우는 구조가 아니라 `NotionMCPClient.session()`으로 세션을 한 번 열어 여러 tool을 재사용하도록 되어 있지만, 검색 1건당 여전히 npx 프로세스 기동 비용이 있어 처음 실행 시 다소 느립니다.
- 과목 태그 표기가 데이터셋 내에서 일관되지 않습니다(예: "통합사회" vs "통합 사회1"). `golden_set/queries.md`의 "노이즈/예외 케이스"에 정리되어 있습니다.

---

# 실전 프로젝트 2: AI 챗봇 기반 수업계획안 생성

## 6. 무엇을 하는 서비스인가

챗봇 창에 과목·학년·주제를 순서대로 물으면 답하는 식으로 순차 대화를 몇 번 주고받으면:

1. LLM(Claude 또는 네이버 클로바)로 8개 섹션(자료 개요, 수업 목표, 배경 읽기 자료, 핵심 개념, 토론 쟁점, 수업 흐름, 학생 활동지 예시, 평가 루브릭)짜리 토의·토론 수업계획안을 생성하고
2. 생성되는 즉시 MCP로 Notion 페이지를 만들어 링크를 보여줍니다(버튼 없이 자동 — 종합 프로젝트에서 이렇게 바꾼 이유는 13-2 참고).
3. 화면에 초안을 보여주면서 자유 텍스트로 수정 요청("토론 쟁점을 3개로 줄여줘")을 받으면 같은 Notion 페이지를 업데이트하고,
4. 원하면 "학생 활동지도 만들기" 버튼으로 활동지를 생성해 Google Docs에 저장하고, 이후 활동지에 영향 있는 수정이면 Google Docs도 자동으로 함께 갱신합니다 (종합 프로젝트 확장분 — 자세한 내용은 11~13번 참고).

(2026-08-26: 1단계의 NCIC 성취기준 조회를 한 차례 완전히 제거했다가(13-7), 강사가 보는 자료에는 근거가 있는 편이 낫다는 판단으로 다시 복원했습니다(13-8) — Quiz Activity는 같은 이유로 복원하지 않았습니다.)

## 7. 실행 방법

실전 1과 사전 준비물(Python, Node.js/npx, Notion Integration)이 동일하고, 추가로 아래가 필요합니다.

- 생성된 수업계획안 페이지를 넣을 Notion 부모 페이지 하나를 만들고, 같은 Integration에 Connections로 연결
- `.env`에 그 페이지 ID를 `NOTION_LESSON_PLAN_PARENT_ID`로 추가 (`.env.example` 참고, 페이지 URL의 32자리 값을 8-4-4-4-12로 나눠 하이픈을 넣으면 됨)
- 계획안 생성에 쓸 LLM 하나: `ANTHROPIC_API_KEY`(Claude, 기본값) 또는 `LLM_PROVIDER=clova` + `HCX_API_KEY`(네이버 클로바 스튜디오) — 아래 8-5 참고

```bash
streamlit run chat_app.py
```

과목→주제를 묻는 질문에 답하는 대화 흐름과 Notion 저장은 크레딧/사용량과 무관하게 확인할 수 있습니다. "계획안을 만드는 중..." 단계만 LLM 호출량이 필요합니다.

## 8. MCP 연동 방식

### 8-1. 전체 구조

```
사용자 메시지
   │
   ▼
conversation.ConversationState   ──▶  과목 → 학년 → 주제 순서로 슬롯 채우기
   (멀티턴 상태 관리)                    (규칙 기반, LLM 불필요)
   │
   ▼
ncic_matcher.match_standards()      ──▶  주제 키워드로 관련 NCIC 성취기준 조회 (없으면 빈 목록, 13-8)
   │
   ▼
lesson_plan.generate_lesson_plan() ──▶  LLM(Claude 또는 클로바)로 8개 섹션 JSON 생성 (NCIC 근거 포함)
   │
   ▼
notion_writer.save/update_lesson_plan_in_notion() ──▶  MCP로 페이지 생성(최초) 또는 본문 갱신(수정), NCIC 근거 섹션 포함
   │
   ▼
chat_app.py (Streamlit)          ──▶  채팅 UI + 초안 표시, 생성/수정 시 자동으로 Notion 반영
```

(종합 프로젝트에서 학생 활동지/Google Docs/수정-전파가 추가된 전체 흐름은 아래 11~13번 참고)

### 8-2. Notion 쓰기 tool 실제 스키마와 겪은 버그들

실전 1은 읽기 전용(`API-post-search` 등)이었지만, 여기서는 쓰기 tool 두 개를 씁니다. 둘 다 실전 1에서 `list_tools()`로 이미 확인해둔 이름이었지만, 실제 호출 스키마는 `scripts/debug_notion_tools.py`로 따로 검증해야 했습니다.

| Tool | 역할 |
|---|---|
| `API-post-page` | `parent`(부모 페이지 ID) + `properties`(제목)로 새 페이지 생성 |
| `API-update-page-markdown` | 생성한 페이지의 본문을 마크다운으로 채워넣기 |

`API-update-page-markdown`은 `page_id`, `type` 두 개가 필수이고, `type`은 `replace_content`(페이지 전체 덮어쓰기, 권장) / `update_content`(부분 find-and-replace, 권장) / `insert_content` / `replace_content_range`(뒤의 둘은 deprecated) 중 하나입니다. 새로 만든 빈 페이지에 계획안 전체를 한 번에 쓰는 용도라 `replace_content`를 씁니다.

실제로 겪은 버그 두 가지 (둘 다 재현 스크립트로 확인 후 수정):

1. **처음엔 `type` 없이 `markdown` 필드만 보내서 검증 에러가 났습니다.** 실제 스키마는 `markdown`이 아니라 `type` + `replace_content: {"new_str": "..."}` 형태를 요구합니다.
2. **notion-mcp-server는 Notion API 검증 에러가 나도 MCP `isError` 플래그를 True로 세팅하지 않습니다.** 에러가 `content[0].text` 안에 `{"object":"error","status":400,...}` 형태의 JSON으로만 실려 옵니다. 그래서 `isError`만 확인하면 실패를 놓칩니다 — 실제로 이것 때문에 페이지는 생성되는데 본문은 계속 비어있는 채로 스크립트가 "성공"이라고 출력했습니다. `notion_writer._raise_if_tool_error()`가 `isError`와 응답 JSON의 `object == "error"` 둘 다 확인하도록 고쳐서 해결했습니다.

이 두 버그는 `scripts/verify_notion_write.py`(LLM 호출 없이 가짜 계획안으로 Notion 쓰기만 검증)로 실제 발견하고 고쳤습니다 — LLM 크레딧이 없어도 이 경로는 크레딧과 무관해서 미리 검증할 수 있었습니다.

### 8-3. NCIC 활용 방식: 단순 키워드 매칭 (RAG·벡터DB 아님)

`ncic_standards/achievement_standards.json`(4,199건, 2022 개정 교육과정 별책 16종에서 초등~고등 전 학년/전 과목을 파싱 — 과제 스펙의 "대상 학년/과목: 전체 제한 없음" 요구사항 반영. 처음엔 고1 공통 과목 5개(157건)로 좁혔다가 스펙을 다시 확인하고 전체로 넓혔습니다. 자세한 배경은 `ncic_standards/README.md` 참고)을 대상으로, 과목명+학년군으로 먼저 후보를 좁히고 주제에서 뽑은 키워드가 성취기준 텍스트에 몇 개나 포함되는지로 점수를 매겨 상위 몇 개만 씁니다. 4천여 건이어도 우리가 직접 정리한 정적 데이터셋이라 필드가 깨끗해서 임베딩 기반 검색 없이도 충분히 정확하고, 임베딩은 보통 유료 API 호출이 필요해서 "크레딧 없이 개발" 방침과도 맞지 않았습니다.

수업계획안의 "NCIC 교육과정 근거" 섹션은 LLM이 문장을 지어내는 게 아니라, `ncic_matcher.match_standards()`가 찾은 항목을 코드/원문 그대로 붙입니다 — 성취기준 코드를 잘못 인용하는 것보다 데이터셋에 실제로 있는 항목만 보여주는 게 안전하다고 판단했습니다.

**2026-08-26 업데이트: 이 NCIC 근거 기능은 한 차례 완전히 제거됐다가(13-7, 18-6-2 — 과목에 따라, 특히 영어는 성취기준 문구가 사용자가 말하는 주제 단위로는 아예 존재하지 않을 수 있는데, 키워드 매칭이 실패하면 무관한 성취기준을 그대로 반환하도록 설계돼 있어서 LLM 프롬프트에 모순된 참고자료가 섞여 들어가는 문제가 실사용 중 발견됐던 것이 계기), 토의·토론(강사가 보는 자료)에 한해 다시 복원됐습니다(13-8).** 복원하면서 원인이었던 폴백 자체를 고쳤습니다 — 키워드가 있는데 전부 0점이면 이제 무관한 상위 N개 대신 빈 목록을 반환합니다(`ncic_matcher.match_standards()`). Quiz Activity는 NCIC 근거를 쓰지 않는 상태를 그대로 유지합니다(18-6-2).

### 8-4. 멀티턴 대화 방식: 순차 질문 수집 → 초안 → 피드백 수정 (혼합형)

`conversation.ConversationState`가 과목 → 학년 → 주제 순서로 정보를 모으고(규칙 기반 키워드 매칭, LLM 불필요), 다 모이면 `lesson_plan.generate_lesson_plan()`을 호출해 초안을 만듭니다. 학년은 "초등학교 3학년"처럼 학교급을 포함해서 답해야 인식됩니다(학교급 없이 "3학년"만 말하면 어느 학년군 성취기준을 찾아야 할지 알 수 없어 재질문합니다). 초안이 나온 뒤 채팅창에 입력하는 내용은 전부 "수정 요청"으로 간주해 재생성합니다. 활동지 생성처럼 "이걸 시작해도 될까"에 해당하는 명시적 승낙 의사는 자유 텍스트가 아니라 버튼으로 받습니다 — "괜찮아요"/"응" 같은 승낙 문구까지 규칙으로 구분하려면 오탐이 잦아지기 때문입니다 (종합 프로젝트에서 활동지 생성 버튼에도 같은 원칙을 그대로 적용했습니다 — 13-2 참고).

이 방식을 택한 이유는 정보 수집 단계를 규칙 기반으로 처리할 수 있어 LLM 크레딧 없이도 대화 흐름 자체는 끝까지 테스트할 수 있었기 때문입니다 (실제 "생성" 한 걸음만 LLM 호출이 필요).

### 8-5. LLM provider 전환: Claude ↔ 네이버 클로바 스튜디오

Claude 크레딧 없이 실제 생성 결과를 검증하기 위해, LLM을 쓰는 모든 기능(실전 1의 요약 `summarizer.py` + 질의분류 `query_router.py`, 실전 2의 계획안 생성 `lesson_plan.py`)이 `src/llm.py`의 `complete(prompt, max_tokens)` 하나만 거치도록 통일했습니다. `.env`의 `LLM_PROVIDER=clova` + `HCX_API_KEY`를 설정하면 이 세 기능 전부 네이버 클로바 스튜디오(HyperCLOVA X)로 요청을 보내고, 비워두면(기본값 `anthropic`) Claude API로 보냅니다. 처음엔 `lesson_plan.py`만 provider를 바꿔 쓰도록 좁게 만들었지만, 이후 실전 1도 같은 클로바 키 하나로 크레딧 없이 전부 검증할 수 있도록 범위를 넓혔습니다.

클로바 스튜디오는 OpenAI 호환 엔드포인트(`https://clovastudio.stream.ntruss.com/v1/openai/`)를 제공해서, 커스텀 HTTP 클라이언트를 새로 짤 필요 없이 `openai` 파이썬 SDK에 `base_url`만 바꿔서 그대로 재사용했습니다.

**실제 클로바 생성 결과로 발견한 버그:** 프롬프트에 "각 값은 문자열로 작성"이라고 명시했는데도, 클로바는 일부 섹션(핵심 개념, 평가 루브릭 등)을 문자열 대신 리스트나 중첩 딕셔너리로 반환하는 경우가 있었습니다(`scripts/verify_lesson_plan_generation.py`로 실제 확인). 그대로 두면 Notion 본문에 `['산업화', '환경오염']` 같은 파이썬 문법이 그대로 노출됩니다 — `lesson_plan._stringify_section()`이 리스트는 글머리 기호 목록으로, 딕셔너리는 `키: 값` 목록으로 정규화하도록 고쳤습니다.

## 9. 프로젝트 구조 (실전 2 추가분)

```
chat_app.py                    # Streamlit 진입점 (챗봇 UI)
src/
  conversation.py              # 멀티턴 대화 상태 관리 (과목/주제 슬롯 채우기, 수정 요청 처리)
  ncic_matcher.py               # NCIC 성취기준 검색 유틸리티 — lesson_plan.py가 사용(토의·토론만, 13-8). Quiz는 사용하지 않음(18-6-2)
  lesson_plan.py                # LLM으로 8개 섹션 수업계획안 생성 (응답 정규화 포함)
  notion_writer.py              # Notion 페이지 생성 + 마크다운 본문 작성 (MCP 쓰기)
  llm.py                        # Claude/클로바 공용 LLM 호출 어댑터 (complete())
ncic_standards/
  achievement_standards.json    # 전체 학년/전체 과목 성취기준 4,199건 (16개 과목)
  README.md                     # 데이터 출처, 스키마, 파싱 방법, 알려진 한계
scripts/
  verify_notion_write.py        # LLM 없이 Notion 쓰기만 수동 검증하는 스크립트
  debug_notion_tools.py         # MCP tool의 실제 입력 스키마를 확인하는 진단 스크립트
  verify_lesson_plan_generation.py  # 실제 LLM 호출로 계획안 생성 결과를 확인하는 스크립트
tests/
  test_conversation.py          # 대화 상태 전이 테스트
  test_ncic_matcher.py          # NCIC 매칭 로직(ncic_matcher.py) 단위 테스트 — 키워드가 있는데 전부 0점이면 빈 목록을 반환하는지 검증(13-8)
  test_lesson_plan.py           # 프롬프트 구성/응답 파싱/정규화 테스트 (LLM 호출은 가짜 함수로 대체)
  test_notion_writer.py         # 마크다운 변환/에러 감지 테스트
  test_llm.py                   # Claude/클로바 provider 분기 테스트
```

## 10. 알려진 제한사항

- **요약/질의분류/계획안 생성 모두 실제로는 클로바(HyperCLOVA X)로만 검증했고, Claude로는 아직 검증 못했습니다.** 코드 경로는 provider에 무관하게 동일하고(`llm.complete()`로 추상화), 클로바로는 계획안 8개 섹션이 모두 정상 생성되는 것을 확인했습니다. Claude 크레딧을 충전하면 `.env`에서 `LLM_PROVIDER`를 비우거나 `anthropic`으로 두고 같은 방식으로 확인하면 됩니다.
- **NCIC 근거 기능은 2026-08-26에 한 차례 제거됐다가(13-7) 토의·토론에 한해 다시 복원됐습니다(13-8).** Quiz Activity는 복원하지 않았습니다(18-6-2). 데이터셋 자체의 알려진 추출 결함(세부 과목명 누락, 일부 수식 텍스트 누락 등)은 `ncic_standards/README.md`에 정리돼 있고, 키워드가 하나도 안 걸리면 이제 무관한 성취기준 대신 빈 목록을 반환하므로(13-8) 예전에 겪었던 무관한 근거가 섞여 들어가는 문제는 재발하지 않습니다.
- LLM이 섹션 값을 문자열이 아닌 리스트/딕셔너리로 반환하는 경우가 있어 `_stringify_section()`으로 정규화합니다(8-5 참고). 아주 깊게 중첩된 구조가 오면 완벽하게 예쁜 포맷은 아닐 수 있습니다.

---

# 종합 프로젝트: AI 기반 수업 활동 에이전트 서비스 (토의·토론 + Quiz Activity)

세 가지 Activity(토의·토론/PBL/Quiz) 중 "최소 1개 이상 완성도 있게 구현"이 요구사항이라, 먼저 실전 2에서 이미 만든 토의·토론 파이프라인을 생성+수정 모두 되는 완성도로 확장했고(11~15번), 이어서 두 번째 Activity로 Quiz(퀴즈 문항 → Google Forms)를 같은 앱에 추가했습니다(16~20번, PBL은 여전히 미구현). 별도 앱을 새로 만들지 않고 `chat_app.py` 위에서 그대로 확장한 이유, 각 설계 결정의 근거, Tool Orchestration 방식은 아래에 정리합니다.

## 11. 실전 2와 달라진 점

실전 2는 "생성해서 Notion에 저장"까지가 끝이었습니다. 종합 프로젝트는 그 뒤에 두 가지가 더 필요합니다.

1. **학생 활동지를 만들어서 Google Docs에 저장** (Notion 하나만 다루던 실전 2에서 외부 서비스가 하나 늘어남)
2. **생성 이후에도 대화로 계속 수정할 수 있고, 수정 결과가 이미 만들어진 외부 문서(Notion 페이지, Google Docs)에도 일관되게 반영** (실전 2는 저장 전 초안 단계에서만 수정이 가능했고, 저장 후에는 손댈 방법이 없었습니다)

## 12. 실행 방법 (실전 2 대비 추가로 필요한 것)

실전 2의 사전 준비물(Python, Node.js/npx, Notion Integration, LLM 키)에 더해 Google Docs 연동을 위한 OAuth 설정이 필요합니다.

1. [Google Cloud Console](https://console.cloud.google.com)에서 프로젝트를 만들고 **Google Docs API**, **Google Drive API**를 활성화
2. OAuth 동의 화면 구성 (User type: External, 테스트 모드로 충분 — 별도 앱 심사 불필요). **테스트 사용자에 본인 Google 계정을 반드시 추가해야 합니다** — 프로젝트 소유자 본인 계정이라도 테스트 사용자 목록에 없으면 "앱이 Google 인증 절차를 완료하지 않았습니다" 오류로 막힙니다.
3. 사용자 인증 정보 → OAuth 클라이언트 ID 생성 (애플리케이션 유형: **데스크톱 앱**) → 다운로드한 JSON을 저장소 루트에 `credentials.json`으로 저장 (`.gitignore`에 이미 포함되어 있어 커밋되지 않습니다)
4. 최초 실행 시 `python scripts/verify_google_docs_auth.py`를 한 번 돌리면 브라우저 인증 후 `token.json`이 생성되고, 이후로는 브라우저 없이 자동 인증됩니다.

```bash
pip install -r requirements.txt
python -m streamlit run chat_app.py   # Windows에서 streamlit이 PATH에 없으면 python -m 필요
```

**겪은 문제 두 가지 (둘 다 코드 문제 아님, 계정/환경 문제):**
- OAuth 동의 화면에서 테스트 사용자 등록을 빼먹으면 위 2번의 오류가 남 — Google Auth Platform > Audience에서 추가하면 해결됩니다.
- Google Drive 저장 공간이 가득 차 있으면 `files().create()`가 `403 storageQuotaExceeded`로 실패합니다 — Drive 웹에서 새 파일을 만들어도 똑같이 막히는 계정 자체의 문제라, 휴지통을 비우는 등 공간을 확보해야 합니다(휴지통에 있는 동안은 용량이 반환되지 않는 점이 놓치기 쉬웠습니다).

## 13. Agent 설계 의도 · Workflow · Tool Orchestration

### 13-1. 왜 Google Docs는 MCP가 아니라 REST API인가

실전 1·2는 `notion-mcp-server`를 로컬 stdio 프로세스로 띄워서 썼습니다. Google Docs도 같은 방식을 먼저 찾아봤지만, 조사 결과(2026-08-10) 세 가지 선택지가 있었고 전부 이 방식을 그대로 재현하기엔 부적합했습니다.

| 선택지 | 문제 |
|---|---|
| 공식 Google Docs 원격 MCP (`docsmcp.googleapis.com`) | Developer Preview 단계. tool이 `read_doc`/`update_doc`뿐이라 **문서 생성 tool이 없음**(Drive MCP의 `create_file`을 따로 조합해야 함). 로컬 stdio가 아니라 원격 HTTP+OAuth 방식이라, notion-mcp-server 때처럼 프로세스만 띄우면 되는 게 아니라 우리 앱이 원격 MCP OAuth 클라이언트를 처음부터 구현해야 함 |
| 커뮤니티 MCP 서버(`google_workspace_mcp` 등) | notion-mcp-server와 같은 로컬 stdio 패턴이라 구조는 맞지만, 비공식/검증되지 않은 코드에 학생 개인정보가 오갈 수 있는 OAuth 인증을 맡기는 셈이라 신뢰성 검증 비용이 큼 |
| REST API 직접 호출 (`google-api-python-client`) | 채택 |

과제 스펙 자체가 "MCP만으로 구현하기 어려운 기능이 있거나 합리적인 이유가 있다면 REST API 등 다른 방식을 함께 사용할 수 있다"고 명시하고 있어, 위 표의 근거로 REST API를 선택했습니다. `google-api-python-client` + OAuth Desktop-app 플로우로 구현했고(`src/google_docs_writer.py`), 스코프는 `documents`와 `drive.file`(이 앱이 만든 파일만 접근 — 드라이브 전체에 접근하는 광범위한 스코프보다 안전)만 요청합니다. Google Forms를 쓰는 Quiz Activity를 나중에 추가한다면 같은 REST API 접근이 필요할 가능성이 높습니다 — Forms는 공식 MCP 서버 자체가 없기 때문입니다.

### 13-2. 생성 흐름: 계획안은 자동 저장, 활동지는 opt-in

과제 스펙의 사용자 시나리오 예시를 보면, 계획안은 생성되자마자 자동으로 Notion에 저장되고("AI Agent는 교육과정을 참고하여 수업계획안을 생성하고 Notion에 저장합니다"), 그다음에야 활동지를 만들지 물어봅니다("학생들이 사용할 활동지도 함께 생성할까요?"). 이 비대칭을 그대로 반영했습니다.

- **계획안**: `_run_generation()`이 생성에 성공하면 그 자리에서 바로 Notion에 반영합니다. 실전 2처럼 "Notion에 저장" 버튼을 따로 두지 않습니다.
- **활동지**: "학생 활동지도 만들기" 버튼을 눌러야 생성됩니다. 채팅으로 "응", "만들어줘" 같은 승낙 문구를 자동 인식하게 만들 수도 있었지만, 8-4에서 이미 채택한 원칙(승낙/거절처럼 되돌리기 부담이 있는 액션은 버튼으로만 받는다 — 자유 텍스트 인식은 오탐 위험)을 그대로 따랐습니다.

### 13-3. 수정 전파: 필드 diff, LLM 재분류 없음

생성 이후 채팅으로 들어오는 모든 메시지는 `conversation.py`의 기존 상태 기계에 따라 "계획안 수정 요청"으로 처리되어 `lesson_plan.generate_lesson_plan(..., revision_request=메시지)`로 계획안 전체를 다시 생성합니다(부분 필드 패치가 아니라 전체 재생성 — 이미 실전 2에 있던 기능을 그대로 재사용). 문제는 그다음입니다: 이 수정이 이미 만들어진 학생 활동지에도 영향을 주는지 어떻게 판단할까.

별도로 "이 수정이 활동지에 영향을 주나요?"를 LLM에게 다시 묻는 방법도 있었지만, 다음 이유로 **필드 diff 방식**(`src/edit_propagation.py`의 `worksheet_needs_update()`)을 택했습니다.

- `worksheet.py`의 프롬프트는 계획안의 `topic`/`subject`/`grade`/`토론_쟁점`/`수업_흐름` 5개 필드만 참고합니다. 수정 전후 계획안에서 이 5개 필드가 하나도 안 바뀌었다면, 활동지를 다시 만들어도 결과가 같을 수밖에 없습니다 — 즉 "영향이 있는가"라는 질문의 답이 이미 코드 안에 있는 정보(활동지가 실제로 읽는 입력이 뭔지)로 결정론적으로 계산됩니다.
- LLM 분류는 크레딧을 한 번 더 쓰고, 애매한 답을 낼 수도 있고, 테스트하기도 어렵습니다. 필드 diff는 순수 함수라 네트워크 없이 유닛 테스트로 완전히 검증됩니다(`tests/test_edit_propagation.py`).

이 판단에 따라 활동지 재생성이 필요하면 `worksheet.generate_worksheet()`을 다시 호출하고 `google_docs_writer.replace_doc_body()`로 같은 문서에 덮어씁니다. Notion 쪽은 판단 없이 항상 `update_lesson_plan_in_notion()`으로 같은 페이지를 업데이트합니다(계획안이 바뀌었다는 사실 자체는 항상 확정적이라 별도 판단이 필요 없습니다). 두 반영 모두 **사용자 확인 없이 자동으로 실행됩니다** — 이미 존재하는 문서를 최신 상태로 유지하는 것이 "일관성 유지"라는 요구사항의 취지에 더 맞는다고 판단했습니다(활동지 최초 생성처럼 "새 문서를 만들지 말지"와는 성격이 다른 결정이라고 봤습니다).

### 13-3-1. 수정 대상 분류: 계획안 vs 활동지

13-3의 설명은 "이 메시지는 계획안 수정 요청"이라고 이미 정해진 다음 얘기입니다. 그런데 실제로는 채팅 메시지가 계획안 얘기("토론 시간을 20분으로")일 수도, 활동지 얘기("활동지 난이도를 낮춰줘")일 수도 있습니다. 처음 버전에서는 이 구분이 아예 없어서 활동지를 겨냥한 요청도 전부 계획안 재생성 프롬프트로 들어갔는데(README 15번에 한계로 적어뒀던 부분), `edit_propagation.classify_edit_target()`을 추가해 메워뒀습니다.

- 메시지에 "활동지"/"학생 활동"/"워크시트"/"활동 자료" 키워드가 있고, 활동지가 이미 만들어져 있으면 → 활동지 수정으로 분류하고 `worksheet.generate_worksheet(plan, revision_request=메시지)`만 다시 호출해 Google Docs에 반영합니다. 계획안/Notion은 건드리지 않습니다.
- 그 외에는 전부 계획안 수정(13-3의 흐름)으로 처리합니다. 활동지가 아직 없으면 키워드가 있어도 무조건 계획안 쪽으로 처리합니다 — 고칠 활동지 자체가 없기 때문입니다(사용자가 "활동지 만들어줘"라고 채팅에 쳐도 버튼을 눌러야 실제로 생성됩니다 — 13-2에서 이미 채택한 원칙과 동일).

여기서도 LLM 재분류 대신 키워드 매칭을 택한 이유는 13-3과 같습니다(크레딧 없이 검증 가능, 결정적, 테스트 쉬움). 다만 이건 필드 diff보다 훨씬 거친 방법이라 한계가 뚜렷합니다 — "쟁점도 줄이고 활동지 질문도 줄여줘"처럼 계획안과 활동지를 한 메시지에서 동시에 언급하면 활동지 쪽으로만 분류되고 계획안 쪽 요청은 반영되지 않습니다. 이 한계는 15번에 그대로 남겨뒀습니다.

### 13-4. 부수적으로 고친 버그

이 작업을 하며 실전 2 코드에 있던 버그 하나를 같이 고쳤습니다: `chat_app.py`가 계획안 생성 실패 여부와 무관하게 `st.rerun()`을 무조건 호출하고 있어서, 실패 메시지가 사용자에게 보이기도 전에 화면이 다시 그려지고 상태가 그대로면 곧바로 재시도가 반복될 수 있었습니다. 종합 프로젝트에서는 생성 성공 시 Notion/Google Docs 쓰기까지 함께 일어나므로 이 재시도 루프가 훨씬 위험해져서(실패한 시도마다 외부 서비스에 불필요한 요청이 반복될 수 있음) 이번에 `_run_generation()`이 성공 여부를 반환하도록 고치고, 호출부는 성공했을 때만 rerun하도록 바꿨습니다.

### 13-5. Tool Routing 요약

이번 Activity는 하나뿐이라 "여러 Activity 중 어느 것을 쓸지 라우팅"하는 로직은 아직 없습니다(15번 참고). 대신 하나의 Activity 안에서 어떤 외부 서비스 호출이 필요한지는 아래처럼 결정됩니다.

| 사용자 행동 | 호출되는 것 |
|---|---|
| 슬롯(과목/학년/주제) 다 채움 | `lesson_plan.generate_lesson_plan()` → `notion_writer.save_lesson_plan_to_notion()` |
| "활동지도 만들기" 버튼 | `worksheet.generate_worksheet()` → `google_docs_writer.create_and_write_doc()` |
| 채팅 수정 요청 (계획안 대상, `classify_edit_target()`이 "plan" 판정) | `lesson_plan.generate_lesson_plan(revision_request=...)` → `notion_writer.update_lesson_plan_in_notion()` → (활동지 존재 + 관련 필드 변경 시) `worksheet.generate_worksheet()` → `google_docs_writer.replace_doc_body()` |
| 채팅 수정 요청 (활동지 대상, `classify_edit_target()`이 "worksheet" 판정) | `worksheet.generate_worksheet(plan, revision_request=...)` → `google_docs_writer.replace_doc_body()` (계획안/Notion 미변경) |

### 13-6. LLM 응답 형식 불안정성: 실패 시 자동 재시도 1회

실제로 겪은 문제(2026-08-11): 클로바가 "JSON만 답하라"는 프롬프트 지시를 가끔 안 지켜서 `generate_worksheet()`이 `WorksheetError("LLM 응답을 활동지 형식으로 해석하지 못했어요")`로 실패했는데, 진단 스크립트(`scripts/debug_worksheet_generation.py`)로 원인을 들여다보니 정상적인 JSON이 아닌 다른 형태로 응답한 순간이 있었을 뿐, 코드 쪽 파싱 로직 문제는 아니었습니다 — 같은 요청을 그대로 다시 보내면 정상적으로 파싱됐습니다.

간헐적 현상이라고 판단해서, `lesson_plan.generate_lesson_plan()`과 `worksheet.generate_worksheet()` 둘 다 첫 시도가 실패하면(형식 오류든 LLM 호출 오류든) 자동으로 한 번만 재시도하고, 그래도 실패하면 그대로 에러를 올려서 사용자가 직접 다시 시도하게 합니다. 무한 재시도가 아니라 "한 번만"으로 제한한 이유는 13-4에서 고친 재시도 루프 버그와 같은 이유입니다 — 실패가 계속되는 상황(예: 크레딧 완전 소진)에서 계속 자동 재시도하면 LLM 호출만 쓸데없이 반복됩니다.

### 13-7. NCIC 근거 기능 제거 (2026-08-26)

8-3에서 설명한 NCIC 근거 매칭(`ncic_matcher.match_standards()`)을 `lesson_plan.py`에서도 제거했습니다. 직접적인 계기는 Quiz Activity(영어 "문법" 주제)에서 발견된 문제였지만 — 성취기준 텍스트에 아예 존재하지 않는 주제로 검색하면 키워드 매칭이 전부 0점이 되고, 그 경우 `match_standards()`가 무관한 성취기준을 그대로 반환하도록 설계돼 있어(관련 성취기준이 하나도 없는 것보다 과목 내 아무거나라도 보여주는 게 낫다는 원래 의도) 프롬프트에 모순된 참고자료가 섞여 들어가는 구조적 문제였습니다 — `lesson_plan.py`도 `quiz.py`와 완전히 같은 `match_standards()` 호출 패턴을 쓰고 있어 동일한 위험을 안고 있었습니다(토의·토론에서는 아직 이 증상이 보고되지 않았지만, 재현 조건이 같아서 시간 문제였을 뿐이라고 판단했습니다). Stanley 결정으로 두 Activity 모두에서 완전히 제거했습니다 — `match_standards()` 호출 자체를 없애서 프롬프트에도 안 들어가게 했고, 화면의 "NCIC 교육과정 근거" 표시도 없앴습니다. `ncic_matcher.py`/데이터셋 파일은 남겨뒀습니다(재사용 가능성, 삭제의 위험 대비 최소 변경 원칙). 자세한 배경과 실제 겪은 증상은 18-6-2 참고 — 두 곳에 중복 설명하지 않으려고 상세 내용은 그쪽에 몰아뒀습니다. 실전 2 스펙에는 "NCIC 근거 제시"가 명시된 요구사항이었기 때문에, 이 제거가 해당 채점 기준과는 안 맞을 수 있다는 점을 인지한 상태에서 내린 결정입니다.

**이 결정은 13-8에서 토의·토론에 한해 다시 뒤집혔습니다** — Quiz는 이 절에서 설명한 상태(NCIC 근거 없음) 그대로 유지됩니다.

### 13-8. NCIC 근거 기능 복원 — 토의·토론 한정 (2026-08-26)

13-7에서 두 Activity 모두 NCIC 근거를 완전히 제거한 뒤, Stanley가 다시 생각해보고 "토의·토론처럼 강사가 보는 자료에는 NCIC 교육과정 근거 박스가 필요할 것 같다"는 판단을 내렸습니다. 강사가 수업을 설계할 때 참고하는 자료(Notion 계획안)와, 학생이 직접 푸는 산출물(Quiz Forms)은 성격이 달라서 근거 표시의 필요성도 다르다고 본 것입니다 — 정리하면:

| Activity | 산출물 성격 | NCIC 근거 |
|---|---|---|
| 토의·토론 | 강사용 수업계획안 (Notion) | 복원 (이 절) |
| Quiz | 학생용 문제/폼 (Google Forms) | 제거 상태 유지 (13-7, 18-6-2) |

복원 범위는 `lesson_plan.py`/`notion_writer.py`/`chat_app.py`(토의·토론 렌더링 부분만)로 한정했고, `quiz.py`/Quiz 쪽 `chat_app.py` 렌더링은 건드리지 않았습니다.

다만 그대로 되돌리면 13-7/18-6-2에서 발견했던 근본 원인(키워드 매칭이 전부 0점일 때 무관한 성취기준을 그대로 반환하는 폴백)이 그대로 남아있는 채로 복원하는 셈이라 같은 문제가 재발할 수 있습니다. 그래서 복원과 함께 `ncic_matcher.match_standards()`의 점수 기반 폴백을 고쳤습니다 — 키워드가 주어졌는데 후보 전부 점수가 0이면, 이제 상위 N개를 억지로 채워 반환하지 않고 빈 목록을 반환합니다. (반면 `keywords` 인자 자체가 비어있는 경우, 즉 애초에 검색할 키워드가 없는 경우의 동작은 건드리지 않았습니다 — 이건 "매칭이 실패"한 것과는 다른 상황이라 범위를 좁혔습니다.) 그 결과 화면에는 근거가 있는 경우에만 "NCIC 교육과정 근거" 박스가 뜨고, 근거가 없으면(예: 영어 "문법"처럼 애초에 매칭될 성취기준이 없는 주제) 조용히 생략됩니다 — 무관한 근거를 억지로 보여주는 대신, 없으면 없는 대로 진행하는 쪽을 택했습니다.

## 14. 프로젝트 구조 (종합 프로젝트 추가분)

```
src/
  worksheet.py               # 학생 활동지 생성 (lesson_plan.py와 같은 패턴, 계획안 dict를 입력으로 받음)
  google_docs_writer.py      # Google Docs REST API 연동 (OAuth Desktop flow, 문서 생성/전체 교체 쓰기)
  edit_propagation.py        # 수정 요청이 계획안/활동지 중 어디를 겨냥한 것인지 + 계획안 수정이 활동지에도 영향을 주는지 판단하는 순수 함수
  notion_writer.py           # (기존 파일에 update_lesson_plan_in_notion 추가 — 같은 페이지 업데이트용)
  conversation.py            # (기존 파일에 notion_page_id/worksheet 관련 상태 필드 추가)
scripts/
  verify_google_docs_auth.py # Google OAuth 인증 + 실제 문서 생성/쓰기를 수동 검증하는 스크립트
  debug_worksheet_generation.py # 활동지 생성 실패 시 LLM 원본 응답을 그대로 출력해 원인을 진단하는 스크립트
tests/
  test_worksheet.py
  test_google_docs_writer.py
  test_edit_propagation.py
```

## 15. 알려진 제한사항

- **PBL Activity는 미구현입니다.** 과제 스펙이 "최소 1개 이상 완성도 있게 구현"을 권장해서, 토의·토론 Activity를 생성+수정+외부 서비스 반영까지 끝까지 완성한 뒤 Quiz Activity(16번)를 추가로 완성하는 쪽을 택했고, PBL은 손대지 않았습니다.
- **수정 대상 분류(계획안 vs 활동지, 13-3-1 참고)가 키워드 매칭이라 거칩니다.** "활동지"/"학생 활동"/"워크시트"/"활동 자료" 키워드로만 판단해서, 두 대상을 한 메시지에 같이 언급하면("쟁점도 줄이고 활동지 질문도 줄여줘") 활동지 쪽으로만 분류되고 계획안 쪽 요청은 무시됩니다. 메시지를 한 번에 하나의 대상만 겨냥하도록 쓰면(현재 UI 안내 문구가 이렇게 유도합니다) 문제없이 동작합니다.
- **Google Docs 활동지는 서식이 없는 순수 텍스트입니다.** Docs API의 `insertText`가 마크다운을 렌더링하지 않아서, 제목/구분선을 굵게·크게 표시하는 등의 서식(`updateTextStyle` 등 추가 batchUpdate 요청)은 아직 넣지 않았습니다.
- Google Docs 연동은 실전 1·2의 "크레딧 없이 개발" 방침과 별개로 **본인 Google 계정의 OAuth 인증과 Drive 저장 공간**이 필요합니다(12번 참고) — 비용은 들지 않지만 계정 설정이 한 단계 더 필요합니다.

---

# 종합 프로젝트: Quiz Activity (퀴즈 문항 → Google Forms)

## 16. 무엇을 하는 서비스인가

`chat_app.py` 상단의 Activity 선택에서 "Quiz"를 고르면:

1. 과목/학년/단원(주제)을 순서대로 물어보는 멀티턴 대화로 정보를 모으고(토의·토론과 같은 `conversation.py` 상태 기계 패턴, `QuizConversationState`)
2. LLM(Claude 또는 네이버 클로바)으로 객관식 문항 5개(보기는 기본 4개, 채팅 수정 요청으로 2~6개 사이 조정 가능)를 JSON으로 생성한 뒤(`quiz.py`)
3. 생성되는 즉시 Google Forms에 새 폼을 만들어(문항 5개 + 각 문항 정답 자동 채점 설정 + 게시까지) 편집 링크와 학생 응답용 링크를 보여주고(`forms_writer.py`)
4. 화면에 문항/정답/해설을 보여주면서 채팅으로 수정 요청("3번 문제를 더 쉽게 해줘")을 받으면 문항 전체를 다시 생성해 같은 폼에 반영합니다.

(2026-08-26: 원래 2단계에 NCIC 성취기준 조회가 있었으나 제거했습니다 — 이유는 18-6-2 참고.)

토의·토론과 달리 산출물이 퀴즈 문항 하나(→ 폼 하나)뿐이라, "이 수정이 어느 문서를 겨냥한 것인지" 분류하는 로직(13-3-1의 `classify_edit_target()`)이 필요 없습니다 — 수정 요청은 항상 전체 재생성 → 같은 폼에 문항 전체 교체입니다.

## 17. 실행 방법 (토의·토론 대비 추가로 필요한 것)

Google Docs 연동(12번)과 동일한 `credentials.json`/OAuth 설정을 그대로 재사용합니다(스코프 `drive.file`이 Forms API의 `create`/`batchUpdate`/`setPublishSettings`도 전부 허용하므로 별도 재동의가 필요 없습니다 — 18-2 참고). 추가로 필요한 건 하나뿐입니다.

1. [Google Cloud Console](https://console.cloud.google.com) > APIs & Services > Library에서 **Google Forms API**(`forms.googleapis.com`)를 검색해 사용 설정(Docs/Drive API를 켰던 것과 같은 화면)
2. (선택) `python scripts/verify_forms_auth.py`로 실제 폼 생성이 되는지 먼저 확인 — Docs 인증(`verify_google_docs_auth.py`)을 이미 통과했다면 `token.json`이 그대로 재사용되어 브라우저 인증 없이 바로 실행됩니다.

```bash
pip install -r requirements.txt
python -m streamlit run chat_app.py   # 실행 후 상단에서 Activity를 "Quiz"로 선택
```

과목→학년→단원을 묻는 대화 흐름은 크레딧과 무관하게 확인할 수 있고, "퀴즈 문항을 만드는 중..." 단계만 LLM 호출이 필요합니다.

## 18. Agent 설계 의도 · Tool Orchestration (Quiz)

### 18-1. Google Forms도 REST API (MCP 없음)

Google Docs 때(13-1)와 같은 이유로 REST API를 택했지만, Forms는 애초에 비교할 선택지 자체가 없었습니다 — 공식이든 커뮤니티든 Google Forms MCP 서버가 존재하지 않는다는 걸 조사로 확인했습니다(2026-08-10 1차 확인, 2026-08-12 재확인). `google-api-python-client`로 `forms` v1 서비스를 직접 호출합니다(`src/forms_writer.py`).

### 18-2. OAuth 스코프 재사용: `drive.file`로 충분, 재동의 불필요

Forms API 문서상 `forms.create`/`forms.batchUpdate`/`forms.setPublishSettings` 세 메서드 모두 `drive`, `drive.file`, `forms.body` 세 스코프 중 아무거나 하나만 있으면 됩니다. Google Docs 연동 때 이미 요청해둔 `drive.file` 스코프가 그대로 해당돼서, `forms.body`를 새로 추가하지 않았습니다(`src/google_auth.py`의 `SCOPES` 그대로 재사용) — 스코프를 넓히면 사용자에게 재동의를 또 요구하게 되는데, 이미 있는 스코프로 충분하다면 그럴 필요가 없다고 판단했습니다.

### 18-3. 겪은 API 함정: 생성 직후엔 응답을 안 받는 폼

Forms API로 만든 폼은 2026-06-30 정책 변경 이후 기본값이 **미게시(UNPUBLISHED)** 상태입니다 — `forms.create`만 호출하고 끝내면 폼은 만들어지지만 학생이 열어도 "응답 받지 않음"으로 나옵니다. `forms_writer.create_quiz_form()`이 문항 생성 배치 요청 뒤에 `forms.setPublishSettings({isPublished: true, isAcceptingResponses: true})`를 명시적으로 한 번 더 호출하도록 해서 해결했습니다. 이 함정은 문서를 읽다가 발견했고, `verify_forms_auth.py`로 실제 응답용 링크가 바로 응답을 받는 상태인지 눈으로 확인하도록 안내를 남겨뒀습니다.

### 18-4. 정답 자동 채점 구조

각 문항은 `questionItem.question.choiceQuestion`(`type: RADIO`)으로 선택지(기본 4개, 요청에 따라 2~6개)를 넣고, `grading.correctAnswers`에 정답 선택지를 지정해 자동 채점을 켭니다(`quizSettings.isQuiz = true`를 폼 전체 설정에 먼저 켜둬야 문항별 `grading`이 의미가 있습니다). 해설은 `grading.whenWrong`에 넣어서, 학생이 오답을 고르면 그 자리에서 해설이 뜨도록 했습니다.

### 18-5. 문항 수정 = 삭제 후 재생성 (Forms API에 "교체" 메서드가 없음)

Forms `batchUpdate`에는 문항을 통째로 바꾸는 단일 요청이 없어서, `replace_quiz_questions()`가 기존 문항을 전부 삭제하는 `deleteItem` 요청과 새 문항을 만드는 `createItem` 요청을 한 batchUpdate에 같이 담아 보냅니다. 삭제는 반드시 **역순**(인덱스가 큰 것부터)으로 넣어야 합니다 — 순서대로 지우면 앞 문항을 지울 때마다 뒤 문항들의 인덱스가 당겨져서 두 번째 삭제 요청이 엉뚱한 문항을 지우게 됩니다(`_delete_all_items_requests()`에 유닛 테스트로 고정해뒀습니다). Google Docs 활동지 수정 때 쓴 "지우고 다시 쓰기" 패턴(`deleteContentRange` + `insertText`)과 같은 발상입니다.

### 18-6. 보기 개수 가변 지원 (2026-08-26)

처음에는 문항당 선택지를 정확히 4개로 고정했었습니다(프롬프트에 "반드시 4개"로 지시하고, `quiz._parse_quiz_json()`이 `len(options) != 4`면 무조건 실패 처리). 실사용 중 "이 문제 보기를 늘려줘" 같은 수정 요청이 왔는데 계속 실패하는 걸 발견하고 원인을 보니, `forms_writer.py`(Forms API로 넘기는 쪽)는 애초에 선택지 개수에 아무 제약이 없는데 `quiz.py`의 검증 로직만 4개로 못 박아둔 상태였습니다 — LLM이 5개짜리로 잘 만들어줘도 검증 단계에서 거부되는 구조였습니다.

`MIN_OPTIONS`(2) / `MAX_OPTIONS`(6) 범위로 완화했습니다. 하한을 2로 둔 건 O/X형 문항도 자연스럽게 허용하기 위함이고, 상한을 6으로 둔 건 Forms 응답 화면에서 보기가 너무 많아지면 가독성이 떨어지고 실수로 정답을 잘못 고를 확률만 올라간다고 판단해서입니다(임의로 정한 값이라 필요하면 조정 가능). `correct_index` 검증도 하드코딩된 `< 4`에서 `< len(options)`로 바꿔서, 보기 개수가 몇 개든 정답 인덱스 범위를 그 문항 기준으로 맞게 확인합니다. 프롬프트에는 "기본 4개, 수정 요청이 있으면 그에 맞게 조정"이라고 명시해 LLM이 매 문항마다 이유 없이 개수를 바꾸지 않도록 유도했습니다.

### 18-6-1. 지목형 수정 요청이 다른 문항까지 깨뜨리는 문제 (2026-08-26)

보기 개수 가변 지원을 실제로 써보다가(Stanley 직접 테스트) "1번 문항을 3개로 줄여줘"라는 수정 요청이 계속 `QuizError`(엉뚱한 문항의 `correct_index` 검증 실패)로 실패하는 걸 발견했습니다. 원인은 검증 로직이 아니라 프롬프트 설계에 있었습니다 — `generate_quiz()`의 수정 요청 경로는 매번 현재 문항 내용을 전혀 보여주지 않고 주제/학년/NCIC 근거 + 수정 요청 텍스트만으로 5개 문항을 백지에서 새로 만들고 있었습니다(`lesson_plan.py`도 원래 같은 패턴). "1번 문항"이 뭔지 LLM이 알 수 없는 상태에서 그 지시를 반영하려다 보니, 지목되지 않은 다른 문항의 형식까지 같이 흔들리는 경우가 생겼습니다.

`generate_quiz()`에 `current_draft` 파라미터를 추가해서(`chat_app.py`의 `_run_quiz_generation()`이 수정 전 draft를 그대로 넘겨줍니다), 수정 요청이 있고 현재 문항이 있으면 `_build_prompt()`가 현재 5개 문항(문항 텍스트 + 보기 + 정답 표시)을 프롬프트에 그대로 포함하고 "언급하지 않은 문항/보기는 원래 내용을 유지하라"고 명시하도록 바꿨습니다. 첫 생성이나 `current_draft`가 없는 경우는 기존 방식(백지에서 생성) 그대로 동작합니다. 종합 프로젝트 스펙 자체가 "3번 문제 단답형으로" 같은 지목형 수정 예시를 들고 있어서, 이 그라운딩은 부가 기능이 아니라 스펙이 요구하는 편집 시나리오를 제대로 지원하기 위한 수정입니다.

### 18-6-2. NCIC 근거 기능 제거 (2026-08-26)

보기 개수 문제(18-6)를 고치고 나서 Stanley가 실제로 "영어 고1 문법" 주제로 퀴즈를 만들어봤는데 문항이 이상하게 나왔습니다. 원인을 데이터로 직접 확인했습니다: `ncic_standards/achievement_standards.json`의 영어 과목 레코드 237건 중 텍스트에 "문법"이라는 단어가 포함된 건 0건이었습니다. 2022 개정 영어과 교육과정 성취기준은 "말이나 글의 세부 정보를 파악한다"처럼 기능(듣기/읽기/말하기/쓰기) 단위로 적혀 있고, 애초에 문법 항목 단위로 성취기준을 쪼개놓지 않았기 때문입니다 — 데이터 파싱 문제가 아니라 국가교육과정 문서 자체의 구성 방식입니다.

문제는 `match_standards()`의 폴백 동작이었습니다: 키워드가 하나도 안 걸리면 빈 목록 대신 해당 과목의 성취기준을 그냥 상위 N개 반환하도록 되어 있었는데(원래 8-3에서 설명한 대로, 수업계획안 생성 맥락에서는 "완전히 없는 것보다 과목 내 아무거나"가 낫다는 의도로 설계), "문법" 검색은 이 폴백에 걸려서 완전히 무관한 독해/듣기 성취기준(예: `10공영1-01-01` "말이나 글에 포함된 세부 정보를 파악한다")이 그대로 프롬프트의 "참고할 국가교육과정 성취기준"으로 들어갔습니다. LLM이 "문법 문제를 내라면서 참고자료는 독해"라는 모순된 지시를 받는 구조였고, 이게 이상한 문항이 나온 유력한 원인으로 판단됩니다.

**결정(Stanley, 2026-08-26): NCIC 근거 기능을 Quiz와 토의·토론 양쪽 모두에서 완전히 제거.** 화면 표시만 숨기는 게 아니라 `match_standards()`/`format_citation()` 호출 자체를 없애서 프롬프트에도 더는 들어가지 않습니다(`quiz.py`/`lesson_plan.py`에서 `extract_keywords()`도 이 용도로만 쓰였어서 같이 제거). `chat_app.py`의 "NCIC 교육과정 근거" 화면 표시(토의·토론/Quiz 둘 다)와 캡션 문구의 "국가교육과정(NCIC) 성취기준에 근거한..." 표현도 제거했습니다. `notion_writer.plan_to_markdown()`의 NCIC 섹션 렌더링 코드도 같이 지웠습니다(더 이상 `ncic_references` 키가 안 들어오므로 죽은 코드였습니다). `ncic_matcher.py` 모듈과 `ncic_standards/` 데이터셋 자체는 삭제하지 않고 남겨뒀습니다 — 되돌리거나 나중에 다른 방식(예: 무관한 성취기준 대신 빈 목록을 반환하는 폴백)으로 재도입할 가능성을 열어두기 위함입니다. 이 결정은 실전 2 스펙의 "NCIC 근거 제시" 요구사항과는 안 맞을 수 있음을 인지한 상태에서 내려졌습니다.

**후속: 여기서 "나중에 다른 방식으로 재도입할 가능성"이라고 남겨둔 대로, 토의·토론에 한해서는 실제로 재도입됐습니다(13-8) — 빈 목록 폴백으로 바로 그 재도입 방식을 그대로 적용했습니다. Quiz는 이 절에서 설명한 제거 상태를 그대로 유지합니다.**

### 18-6-3. 정답 인덱스가 해설과 어긋나는 버그 수정 (2026-08-26)

Stanley가 실사용 중 발견한 문제입니다: "축구에서 득점을 올리는 것을 무엇이라고 부르나요?" 문항에서 해설(explanation)은 "'골'이라고 부릅니다"로 정확했는데, 실제로 만들어진 Google Forms에서 정답으로 체크된 보기는 "세이브"였습니다. 코드를 추적해보니 `forms_writer._question_item()`은 `options[correct_index]`를 그대로 Forms의 `grading.correctAnswers`에 넣고 있어서, 버그가 있다면 그 앞 단계 — `quiz.py`가 LLM으로부터 받는 `correct_index` 자체 — 라고 좁혀졌습니다. 기존 검증(`0 <= correct_index < len(options)`)은 범위 안의 정수인지만 확인할 뿐, 그 인덱스가 실제로 해설이 가리키는 보기와 같은 문항을 가리키는지는 확인할 방법이 없는 구조였습니다 — JSON 자체는 완전히 유효했기 때문에 기존 재시도 로직(형식 오류 시 1회 재시도)도 이 문제를 걸러내지 못했습니다.

같은 문항 안에서 해설 문장은 정답을 말로 정확히 서술하면서, 그 정답이 `options` 배열의 몇 번째인지 세는 과정에서만 다른 값을 내놓는 비일관성이 원인으로 보입니다 — LLM이 "정답이 뭔지"는 잘 알지만 "그게 몇 번째 보기인지"를 세는 부가 작업에서 가끔 실수하는 유형의 오류라고 판단했습니다. 그래서 애초에 인덱스를 세는 작업 자체를 LLM에게 요구하지 않기로 했습니다 — 프롬프트의 JSON 스키마를 `correct_index`(정답 선택지의 인덱스)에서 `correct_answer`(정답 선택지의 텍스트를 `options` 중 하나와 완전히 동일하게 옮겨 적기)로 바꾸고, `quiz._parse_quiz_json()`이 파싱 단계에서 문자열 일치로 `correct_index`를 역산합니다. 일치하는 보기가 없으면(오타 등으로 `options`에 없는 문자열을 적은 경우) `QuizError`를 올려서 기존 1회 재시도 정책이 그대로 작동하게 했습니다 — 조용히 틀린 정답을 쓰는 것보다 재시도하는 편이 안전하다고 판단했습니다. `forms_writer.py`/`chat_app.py` 등 나머지 코드는 그대로 `correct_index`를 쓰므로 이 변경은 `quiz.py`의 생성/파싱 단계에만 국한됩니다.

### 18-7. 나머지는 토의·토론과 동일한 패턴 재사용

- **멀티턴 대화**: `QuizConversationState`가 `ConversationState`와 같은 `Phase`(COLLECTING→READY→DRAFTED→REVISING) 흐름을 따르되, 산출물이 하나뿐이라 훨씬 단순합니다. 두 클래스를 공통 베이스로 합치지는 않았습니다 — 이미 테스트를 통과한 기존 코드를 건드릴 위험을 감수할 만큼 중복이 크지 않다고 판단했습니다(`lesson_plan.py`/`worksheet.py`/`quiz.py`를 각각 독립 모듈로 둔 것과 같은 원칙).
- **재시도 정책**: 클로바의 간헐적 JSON 형식 미준수(13-6)에 대응해 `quiz.py`도 `_generate_once()` 헬퍼로 실패 시 한 번만 자동 재시도합니다.
- **재시도 루프 방지**: `_run_quiz_generation()`도 `_run_generation()`(13-4)과 같은 이유로 성공 여부를 반환해서, 실패했을 때 `chat_app.py`가 무조건 rerun하지 않도록 했습니다.

### 18-8. Activity 선택 UI

`chat_app.py` 최상단에 `st.radio(["토의·토론", "Quiz"])`를 두고, 그 아래 전체를 이 선택값으로 분기합니다. 두 Activity의 상태(`st.session_state.conv`, `st.session_state.quiz_conv`)는 서로 독립적으로 유지되어서, 라디오를 왔다갔다 눌러도 각 Activity에서 진행 중이던 대화/초안이 그대로 남아있습니다. 하나의 앱으로 통합한 것은 "여러 Activity를 하나의 서비스에서 고를 수 있게 하자"는 방향으로 결정한 데 따른 것입니다(2026-08-12).

## 19. 프로젝트 구조 (Quiz Activity 추가분)

```
src/
  google_auth.py             # Google OAuth 공용 모듈 (google_docs_writer.py에서 추출, Docs/Forms 공용)
  forms_writer.py            # Google Forms REST API 연동 (폼 생성+게시, 문항 생성/삭제, 정답 자동 채점)
  quiz.py                    # LLM으로 객관식 퀴즈 문항 5개 생성, 보기 개수 2~6개(기본 4개) 가변 (lesson_plan.py/worksheet.py와 같은 패턴)
  conversation.py            # (기존 파일에 QuizConversationState 추가 — ConversationState와 동일한 Phase 흐름)
chat_app.py                  # (Activity 선택 라디오 추가, 토의·토론/Quiz 렌더링 함수로 분리)
scripts/
  verify_forms_auth.py       # Google Forms OAuth 인증 + 실제 폼 생성/게시를 수동 검증하는 스크립트
tests/
  test_forms_writer.py       # 문항 변환/삭제 순서(역순) 등 순수 함수 테스트
  test_quiz.py                # 프롬프트 구성/응답 파싱·검증 테스트 (LLM 호출은 가짜 함수로 대체)
  test_quiz_conversation.py   # QuizConversationState 상태 전이 테스트
```

## 20. 알려진 제한사항 (Quiz)

- **수정 요청은 항상 문항 전체를 재생성합니다.** "3번만 고쳐줘"처럼 문항 하나만 겨냥해도 5문항 전체가 다시 만들어지고 폼도 전체 재생성됩니다(18-5) — 산출물이 하나뿐이라 부분 수정보다 훨씬 단순하게 구현할 수 있었지만, 그만큼 안 건드려도 되는 문항까지 매번 다시 생성되는 비용이 있습니다. 다만 2026-08-26부터는 현재 문항 내용을 프롬프트에 같이 넣어서(18-6-1) 지목한 문항을 정확히 찾아 고치도록 유도하므로, 재생성은 하되 무관한 문항이 같이 바뀔 위험은 줄였습니다 — 그래도 LLM이 지시를 완벽히 따른다는 보장은 없습니다.
- **문항 유형은 객관식(RADIO)만 지원합니다.** 서술형·단답형 등 다른 유형은 만들지 않습니다. (보기 개수 자체는 기본 4개이며 2~6개 사이에서 채팅 수정 요청으로 조정할 수 있습니다 — 2026-08-26에 고정 4지선다에서 확장, 18-6 참고.)
- **정답 자동 채점 확인은 실제 클로바 응답으로만 검증했습니다.** Claude 크레딧을 충전하면 8-5와 같은 방식으로 `.env`의 `LLM_PROVIDER`를 바꿔 같은 경로로 확인할 수 있습니다.
- **NCIC 근거 기능은 Quiz에서는 제거된 상태입니다** (18-6-2, 13-7 참고) — 토의·토론에서는 이후 다시 복원됐지만(13-8), Quiz는 학생용 산출물이라는 성격상 복원하지 않기로 했습니다. 이제 이 항목은 알려진 제한사항이 아니라 완료된 설계 변경입니다.
- Forms API 사용은 Docs와 마찬가지로 **본인 Google 계정의 OAuth 인증**이 필요합니다(17번 참고) — 비용은 들지 않지만 GCP 콘솔에서 Forms API를 별도로 켜야 합니다.

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

### A-3. 실전 프로젝트 2 — AI 챗봇 기반 수업계획안 생성 (구현 완료 — 상세는 위 6~10번 참고)

**개요:** 사용자와 멀티턴 대화를 통해 토의·토론 수업계획안을 완성하고, 국가교육과정(NCIC) 근거를 제시하며 Notion 페이지까지 생성하는 챗봇.

**필수 기능**
- 챗봇 인터페이스 + 멀티턴 대화
- 토의·토론 수업계획안 생성 (자료 개요, 수업 목표, 배경 읽기 자료, 핵심 개념, 토론 쟁점, 수업 흐름, 학생 활동지 예시, 평가 루브릭)
- NCIC 교육과정 근거 제시 (성취기준 코드, 관련 성취기준, 참고 원문/링크)
- Notion 페이지 생성 및 링크 반환
- 예외 상황 처리

**구현 조건:** Notion 페이지 생성은 MCP로, LLM으로 대화 관리 및 계획안 생성, 프론트엔드는 챗봇 UI 단일 화면.

**사전 조사 필요:** MCP를 통한 Notion 쓰기 방식, NCIC 자료 활용 방식(검색/RAG/벡터DB), 멀티턴 대화 상태 관리 방식.

### A-4. 종합 프로젝트 — AI 기반 수업 활동 에이전트 서비스 (토의·토론 + Quiz 구현 완료 — 상세는 위 11~20번 참고)

**개요:** 교사의 수업 활동(토의·토론, 프로젝트 학습, 퀴즈)에 특화된 AI Agent를 설계하고, 여러 외부 서비스와 연동해 수업자료를 생성·수정하는 서비스. 핵심은 "Tool을 몇 개 연결했는가"가 아니라 "사용자에게 자연스러운 Workflow를 어떻게 설계했는가".

**Activity 3종 (최소 1개 이상 완성도 있게 구현 권장)**

| Activity | 생성/수정 대상 | 연동 서비스 | 예시 요청 |
|---|---|---|---|
| 토의·토론 (구현 완료) | 수업계획안, 학생 활동지 | Notion, Google Docs | "고1 사회 토의 수업을 준비해줘." |
| 프로젝트(PBL) (미구현) | 수업계획안, 학생 활동지 | Notion, Google Docs | "환경 문제 프로젝트 수업을 만들어줘." |
| Quiz (구현 완료) | 퀴즈 문항 | Google Forms | "삼각형 단원 퀴즈를 만들어줘." |

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
- **Activity 선택 (종합):** 토의·토론 / PBL / Quiz 중 몇 개를 구현할지 — 토의·토론, Quiz 2개 구현, PBL은 미구현으로 결정
- **외부 서비스 연동 방식:** MCP 전용 vs MCP+REST API 병행
- **선택 기능 채택 여부:** 생성 과정 시각화·이력 관리, Padlet 연동 등 추가 기능

---

*이 문서는 2026-08-12 기준으로 갱신되었습니다 (실전 프로젝트 1·2 + 종합 프로젝트 토의·토론 + Quiz Activity 구현 반영). PBL Activity를 추가로 구현하면 추가 갱신이 필요합니다.*
