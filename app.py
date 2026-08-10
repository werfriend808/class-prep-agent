"""실전 프로젝트 1: MCP 기반 Notion 페이지 검색 및 요약 - Streamlit 앱.

실행: streamlit run app.py

사전 준비 (README 참고):
    - Node.js / npx 설치 (notion-mcp-server 구동용)
    - .env에 NOTION_API_KEY 설정, 요약/분류용 LLM 키(ANTHROPIC_API_KEY 또는
      LLM_PROVIDER=clova + HCX_API_KEY) 설정
    - FILTER(학년/과목/날짜) 검색을 쓰려면 .env에 NOTION_DATA_SOURCE_ID도 설정
"""
import asyncio

import streamlit as st

from src.pipeline import search_and_summarize

st.set_page_config(page_title="수업 자료 검색", page_icon="🔍", layout="centered")

st.title("수업 자료 검색")
st.caption("Notion에 있는 수업 자료를 자연어로 검색하고 요약해서 보여드려요.")

query = st.text_input(
    "검색어",
    placeholder="예: 토론 수업 진행 방법 관련 페이지 찾아줘",
    label_visibility="collapsed",
)
search_clicked = st.button("검색", type="primary")

if search_clicked and query.strip():
    try:
        with st.spinner("검색하고 요약하는 중..."):
            results = asyncio.run(search_and_summarize(query))
    except RuntimeError as e:
        # 설정 누락(NOTION_DATA_SOURCE_ID, API 키 등) 같은 예상 가능한 오류
        st.error(str(e))
    except Exception as e:  # noqa: BLE001 — MCP 프로세스/네트워크 오류 등 예상 밖 오류
        st.error(f"검색 중 문제가 발생했어요: {e}")
    else:
        if not results:
            st.info("관련 페이지를 찾지 못했어요. 다른 검색어로 시도해보세요.")
        else:
            st.write(f"관련 페이지 {len(results)}건을 찾았어요.")
            for r in results:
                with st.container(border=True):
                    col1, col2 = st.columns([5, 1])
                    with col1:
                        st.markdown(f"**{r.title}**")
                    with col2:
                        st.markdown(f"[Notion에서 열기]({r.notion_url})")
                    if r.tags:
                        st.write(" ".join(f"`{t}`" for t in r.tags))
                    st.write(r.summary)
elif search_clicked:
    st.warning("검색어를 입력해주세요.")
