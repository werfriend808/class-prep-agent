"""실전 프로젝트 2: AI 챗봇 기반 수업계획안 생성 - Streamlit 앱.

실행: streamlit run chat_app.py (실전 1의 app.py와는 별도 진입점)

흐름: 멀티턴으로 과목/주제를 수집(conversation.py) -> 수업계획안 생성
      (lesson_plan.py, NCIC 근거는 ncic_matcher.py에서) -> 사용자가 확인 후
      "Notion에 저장" 버튼으로 Notion 페이지 생성(notion_writer.py).

주의: 계획안 "생성" 자체가 LLM 호출이라(.env의 LLM_PROVIDER에 따라 Claude 또는
네이버 클로바) 크레딧/사용량이 없으면 이 부분만 막힌다 (검색 위주였던 실전 1과
다른 지점 — README 참고). 대화 흐름과 Notion 저장은 크레딧과 무관하게 동작한다.
"""
import asyncio

import streamlit as st

from src.conversation import ConversationState, Phase
from src.lesson_plan import LessonPlanError, generate_lesson_plan
from src.ncic_matcher import available_subjects
from src.notion_writer import NotionWriteError, save_lesson_plan_to_notion

st.set_page_config(page_title="수업계획안 챗봇", page_icon="💬", layout="centered")

st.title("토의·토론 수업계획안 챗봇")
st.caption(
    f"과목({', '.join(available_subjects())})과 주제를 알려주시면 국가교육과정(NCIC) 성취기준에 "
    "근거한 토의·토론 수업계획안을 만들어드려요."
)

if "conv" not in st.session_state:
    st.session_state.conv = ConversationState()
    st.session_state.conv.history.append(
        {"role": "assistant", "content": st.session_state.conv.next_question()}
    )

conv: ConversationState = st.session_state.conv


def _run_generation(revision_request: str | None = None) -> None:
    slots = conv.slots
    try:
        with st.spinner("수업계획안을 만드는 중..."):
            plan = generate_lesson_plan(
                subject=slots["subject"],
                topic=slots["topic"],
                grade=slots.get("grade", "고1"),
                revision_request=revision_request,
            )
    except LessonPlanError as e:
        st.error(str(e))
        # 생성 실패 시 REVISING/READY 상태에 머물러 재시도할 수 있게 둔다.
        return
    conv.apply_draft(plan)


# --- 대화창 ---
for msg in conv.history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("메시지를 입력하세요")
if user_input:
    with st.chat_message("user"):
        st.write(user_input)
    reply = conv.handle_message(user_input)
    with st.chat_message("assistant"):
        st.write(reply)
    st.rerun()

# --- READY: 슬롯이 다 채워졌으면 자동으로 생성 트리거 ---
if conv.phase == Phase.READY:
    _run_generation()
    st.rerun()

# --- REVISING: 수정 요청 반영해서 재생성 ---
if conv.phase == Phase.REVISING:
    _run_generation(revision_request=conv.slots.get("revision_request"))
    st.rerun()

# --- DRAFTED: 초안 보여주고 저장/재수정 액션 제공 ---
if conv.phase == Phase.DRAFTED and conv.draft:
    plan = conv.draft
    st.divider()
    st.subheader(f"{plan['topic']} — {plan['subject']} 토의·토론 수업계획안")

    section_titles = {
        "자료_개요": "자료 개요",
        "수업_목표": "수업 목표",
        "배경_읽기_자료": "배경 읽기 자료",
        "핵심_개념": "핵심 개념",
        "토론_쟁점": "토론 쟁점",
        "수업_흐름": "수업 흐름",
        "학생_활동지_예시": "학생 활동지 예시",
        "평가_루브릭": "평가 루브릭",
    }
    for key, label in section_titles.items():
        with st.expander(label, expanded=(key in ("자료_개요", "수업_목표"))):
            st.write(plan.get(key, ""))

    if plan.get("ncic_references"):
        with st.expander("NCIC 교육과정 근거", expanded=False):
            for ref in plan["ncic_references"]:
                st.write(f"- {ref}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Notion에 저장", type="primary", key="save_notion"):
            try:
                with st.spinner("Notion 페이지를 만드는 중..."):
                    result = asyncio.run(save_lesson_plan_to_notion(plan))
            except NotionWriteError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001 — MCP 프로세스/네트워크 오류 등
                st.error(f"Notion 저장 중 문제가 발생했어요: {e}")
            else:
                conv.notion_url = result["url"]
    with col2:
        if st.button("새로 만들기", key="reset"):
            conv.reset()
            conv.history.append({"role": "assistant", "content": conv.next_question()})
            st.rerun()

    if conv.notion_url:
        st.success(f"Notion 페이지를 만들었어요: [{conv.notion_url}]({conv.notion_url})")

    st.caption("수정하고 싶은 점이 있으면 위 채팅창에 자유롭게 적어주세요 (예: '토론 쟁점을 3개로 줄여줘').")
