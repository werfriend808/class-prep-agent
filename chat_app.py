"""토의·토론 Activity 챗봇 — 실전 프로젝트 2에서 시작해 종합 프로젝트로 확장.

실행: streamlit run chat_app.py (실전 1의 app.py와는 별도 진입점)

흐름: 멀티턴으로 과목/주제를 수집(conversation.py) -> 수업계획안 생성
      (lesson_plan.py, NCIC 근거는 ncic_matcher.py에서) -> 생성되는 즉시
      Notion에 자동 반영(notion_writer.py) -> 사용자가 원하면 버튼으로 학생
      활동지 생성(worksheet.py) -> Google Docs에 자동 반영(google_docs_writer.py).

종합 프로젝트의 핵심 차이(실전 2와 다른 점): 생성 이후에도 채팅으로 계속
수정을 요청할 수 있고, 수정 결과는 매번 같은 Notion 페이지에 반영된다
(새 페이지를 만들지 않음). 활동지가 이미 만들어져 있는 상태에서 활동지에도
영향을 주는 수정(주제/과목/학년/토론 쟁점/수업 흐름 변경)이면 활동지도
자동으로 다시 만들어 Google Docs에 반영한다 — 판단 로직은
edit_propagation.worksheet_needs_update() 참고.

주의: 계획안/활동지 "생성" 자체는 LLM 호출이라(.env의 LLM_PROVIDER에 따라
Claude 또는 네이버 클로바) 크레딧/사용량이 없으면 이 부분만 막힌다. 대화
흐름과 Notion/Docs 반영 자체는 크레딧과 무관하게 동작한다.
"""
import asyncio

import streamlit as st

from src.conversation import ConversationState, Phase
from src.edit_propagation import worksheet_needs_update
from src.google_docs_writer import GoogleDocsWriteError, create_and_write_doc, replace_doc_body
from src.lesson_plan import LessonPlanError, generate_lesson_plan
from src.ncic_matcher import available_subjects
from src.notion_writer import NotionWriteError, save_lesson_plan_to_notion, update_lesson_plan_in_notion
from src.worksheet import WorksheetError, generate_worksheet, worksheet_to_text

st.set_page_config(page_title="수업계획안 챗봇", page_icon="💬", layout="centered")

st.title("토의·토론 수업계획안 챗봇")
st.caption(
    f"과목({', '.join(available_subjects())}), 학년, 주제를 알려주시면 국가교육과정(NCIC) 성취기준에 "
    "근거한 토의·토론 수업계획안을 만들고 Notion에 자동으로 저장해드려요. 생성 후에도 채팅으로 "
    "계속 수정을 요청할 수 있고, 원하면 학생 활동지도 만들어서 Google Docs에 저장할 수 있어요."
)

if "conv" not in st.session_state:
    st.session_state.conv = ConversationState()
    st.session_state.conv.history.append(
        {"role": "assistant", "content": st.session_state.conv.next_question()}
    )

conv: ConversationState = st.session_state.conv

PLAN_SECTION_TITLES = {
    "자료_개요": "자료 개요",
    "수업_목표": "수업 목표",
    "배경_읽기_자료": "배경 읽기 자료",
    "핵심_개념": "핵심 개념",
    "토론_쟁점": "토론 쟁점",
    "수업_흐름": "수업 흐름",
    "학생_활동지_예시": "학생 활동지 예시",
    "평가_루브릭": "평가 루브릭",
}

WORKSHEET_SECTION_TITLES = {
    "활동_안내": "활동 안내",
    "배경_자료_요약": "배경 자료 요약",
    "토론_질문": "토론 질문",
    "개인_의견_작성란": "개인 의견 작성란",
    "모둠_토의_기록표": "모둠 토의 기록표",
    "소감_정리": "소감 정리",
}


def _sync_notion(plan: dict) -> None:
    """계획안을 Notion에 반영한다. 처음이면 새 페이지, 이미 있으면 같은 페이지를 업데이트한다."""
    try:
        with st.spinner("Notion에 반영하는 중..."):
            if conv.notion_page_id:
                result = asyncio.run(update_lesson_plan_in_notion(conv.notion_page_id, plan))
            else:
                result = asyncio.run(save_lesson_plan_to_notion(plan))
    except NotionWriteError as e:
        st.error(f"Notion 반영에 실패했어요: {e}")
    except Exception as e:  # noqa: BLE001 — MCP 프로세스/네트워크 오류 등
        st.error(f"Notion 반영 중 문제가 발생했어요: {e}")
    else:
        conv.notion_page_id = result["page_id"]
        conv.notion_url = result["url"]


def _sync_worksheet_if_needed(old_plan: dict | None, plan: dict) -> None:
    """활동지가 이미 있고 이번 수정이 활동지에도 영향을 준다면, 자동으로 다시 만들어 Google Docs에 반영한다."""
    if not conv.worksheet_doc_id or not worksheet_needs_update(old_plan, plan):
        return
    try:
        with st.spinner("계획안 변경 내용을 학생 활동지에도 반영하는 중..."):
            new_worksheet = generate_worksheet(plan)
            replace_doc_body(conv.worksheet_doc_id, worksheet_to_text(new_worksheet))
    except WorksheetError as e:
        st.error(f"학생 활동지 재생성에 실패했어요: {e}")
    except GoogleDocsWriteError as e:
        st.error(f"Google Docs 반영에 실패했어요: {e}")
    except Exception as e:  # noqa: BLE001
        st.error(f"활동지 업데이트 중 문제가 발생했어요: {e}")
    else:
        conv.worksheet = new_worksheet


def _run_generation(revision_request: str | None = None) -> bool:
    """계획안을 (재)생성하고 Notion/활동지에 동기화한다. 성공하면 True를 반환한다.

    실패해도 무조건 rerun하지 않게 호출부에서 반환값을 확인한다 — 그렇지
    않으면 실패 -> 즉시 rerun -> 같은 상태라 즉시 재시도가 반복되면서 LLM을
    쓸데없이 계속 호출하게 된다 (특히 지금은 성공 시 Notion/Docs 쓰기까지
    딸려있어서 이 무한 재시도가 훨씬 더 위험하다).
    """
    slots = conv.slots
    old_plan = conv.draft
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
        if old_plan is not None:
            # 수정 시도가 실패한 거라면 이전 초안으로 되돌아가서 다시 보여준다.
            conv.phase = Phase.DRAFTED
        return False

    conv.apply_draft(plan)
    _sync_notion(plan)
    _sync_worksheet_if_needed(old_plan, plan)
    return True


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
    if _run_generation():
        st.rerun()

# --- REVISING: 수정 요청 반영해서 재생성 (+ Notion/활동지 자동 동기화) ---
if conv.phase == Phase.REVISING:
    if _run_generation(revision_request=conv.slots.get("revision_request")):
        st.rerun()

# --- DRAFTED: 계획안(+ 있으면 활동지) 보여주고, 활동지 생성/재시작 액션 제공 ---
if conv.phase == Phase.DRAFTED and conv.draft:
    plan = conv.draft
    st.divider()
    st.subheader(f"{plan['topic']} — {plan['subject']} 토의·토론 수업계획안")

    for key, label in PLAN_SECTION_TITLES.items():
        with st.expander(label, expanded=(key in ("자료_개요", "수업_목표"))):
            st.write(plan.get(key, ""))

    if plan.get("ncic_references"):
        with st.expander("NCIC 교육과정 근거", expanded=False):
            for ref in plan["ncic_references"]:
                st.write(f"- {ref}")

    if conv.notion_url:
        st.success(f"Notion에 반영됨: [{conv.notion_url}]({conv.notion_url})")
    else:
        st.warning("아직 Notion에 반영되지 않았어요. 위쪽 오류 메시지를 확인해주세요.")

    st.divider()
    if not conv.worksheet_doc_id:
        st.caption("학생들이 수업 중 직접 쓸 활동지도 만들어서 Google Docs에 저장할 수 있어요.")
        if st.button("학생 활동지도 만들기", key="make_worksheet"):
            try:
                with st.spinner("학생 활동지를 만드는 중..."):
                    worksheet_data = generate_worksheet(plan)
                    doc = create_and_write_doc(
                        f"{plan['topic']} 학생 활동지",
                        worksheet_to_text(worksheet_data),
                    )
            except WorksheetError as e:
                st.error(str(e))
            except GoogleDocsWriteError as e:
                st.error(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"활동지 생성 중 문제가 발생했어요: {e}")
            else:
                conv.worksheet = worksheet_data
                conv.worksheet_doc_id = doc["doc_id"]
                conv.worksheet_url = doc["url"]
                st.rerun()
    else:
        st.success(f"학생 활동지: [{conv.worksheet_url}]({conv.worksheet_url})")
        with st.expander("학생 활동지 미리보기", expanded=False):
            for key, label in WORKSHEET_SECTION_TITLES.items():
                st.write(f"**{label}**")
                st.write(conv.worksheet.get(key, "") if conv.worksheet else "")

    st.divider()
    if st.button("새로 만들기", key="reset"):
        conv.reset()
        conv.history.append({"role": "assistant", "content": conv.next_question()})
        st.rerun()

    st.caption(
        "수정하고 싶은 점이 있으면 위 채팅창에 자유롭게 적어주세요 (예: '토론 쟁점을 3개로 줄여줘', "
        "'토론 시간을 20분으로 늘려줘'). 계획안 수정 결과는 Notion에, 활동지에 영향 있는 수정이면 "
        "학생 활동지(Google Docs)에도 자동으로 반영돼요."
    )
