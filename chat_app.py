"""AI 기반 수업 활동 에이전트 — 종합 프로젝트, Activity 2종(토의·토론/Quiz) 통합 앱.

실행: streamlit run chat_app.py (실전 1의 app.py와는 별도 진입점)

Activity 선택 화면(스펙 필수 UI 요소) 하나에서 두 Activity를 고를 수 있다.
앱을 둘로 쪼개지 않고 한 파일 안에서 라디오로 분기한 이유는 "여러 Activity를
통합해 하나의 서비스로 구현할 수 있다"는 스펙 취지에 맞추기 위함이다
(2026-08-12 결정, Stanley 확인).

**토의·토론 Activity** (실전 프로젝트 2에서 시작해 확장):
    멀티턴으로 과목/학년/주제 수집(conversation.ConversationState) -> 수업계획안
    생성(lesson_plan.py, NCIC 근거는 ncic_matcher.py — 2026-08-26 한때 제거했다가
    강사용 자료엔 필요하다고 판단해 폴백을 고쳐서 복원, README 13-7) -> 생성되는 즉시 Notion에
    자동 반영(notion_writer.py) -> 사용자가 원하면 버튼으로 학생 활동지 생성
    (worksheet.py) -> Google Docs에 자동 반영(google_docs_writer.py). 생성 후
    채팅 수정 요청은 edit_propagation.classify_edit_target()으로 계획안/활동지
    중 어느 쪽 얘기인지 구분해서 해당 문서만 갱신한다 — 활동지 관련 필드
    (주제/과목/학년/토론 쟁점/수업 흐름)가 바뀌면 활동지도 자동으로 같이
    갱신된다(edit_propagation.worksheet_needs_update()).

**Quiz Activity** (2026-08-12 신규, 2026-08-26 보기 개수 가변 지원 추가):
    멀티턴으로 과목/학년/단원 수집(conversation.QuizConversationState) -> 객관식(기본
    4지선다, 요청 시 2~6개로 조정) 퀴즈 문항 생성(quiz.py) -> 생성되는 즉시 Google
    Forms에 자동 반영(forms_writer.py — 폼 생성 + 객관식 문항 + 정답/배점 +
    게시). 산출물이 폼 하나뿐이라 계획안/활동지처럼 "어느 문서 얘기인지"
    분류할 필요가 없다 — 채팅 수정 요청은 항상 문항 전체를 다시 만들어 같은
    폼에 반영한다.

주의: 계획안/활동지/퀴즈 문항 "생성" 자체는 LLM 호출이라(.env의 LLM_PROVIDER에
따라 Claude 또는 네이버 클로바) 크레딧/사용량이 없으면 이 부분만 막힌다. 대화
흐름과 Notion/Docs/Forms 반영 자체는 크레딧과 무관하게 동작한다.
"""
import asyncio

import streamlit as st

from src.conversation import ConversationState, Phase, QuizConversationState
from src.curriculum import get_provider
from src.edit_propagation import classify_edit_target, worksheet_needs_update
from src.forms_writer import FormsWriteError, create_quiz_form, replace_quiz_questions
from src.google_docs_writer import GoogleDocsWriteError, create_and_write_doc, replace_doc_body
from src.lesson_plan import LessonPlanError, generate_lesson_plan
from src.notion_writer import NotionWriteError, save_lesson_plan_to_notion, update_lesson_plan_in_notion
from src.quiz import QuizError, generate_quiz
from src.worksheet import WorksheetError, generate_worksheet, worksheet_to_text

st.set_page_config(page_title="AI 수업 활동 에이전트", page_icon="💬", layout="centered")

# 시각적 다듬기(2026-08-12): 색상/폰트는 .streamlit/config.toml의 테마 설정을
# 우선 쓰고(네이비/그레이 + teal 포인트 컬러), 테마만으로 안 되는 세부 스타일
# (카드 느낌 테두리, 여백 등)만 최소한으로 CSS를 얹는다. data-testid 셀렉터를
# 쓴 이유: Streamlit이 자동 생성하는 클래스 이름(css-xxxx)보다 testid가 버전
# 업데이트에 비교적 덜 취약하다 — 그래도 공식 안정 API는 아니라서, 버전이
# 바뀌어 셀렉터가 안 맞아도 최악의 경우 스타일만 안 먹고 기능은 그대로 동작한다.
st.markdown(
    """
    <style>
    div[data-testid="stExpander"] {
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    div[data-testid="stAlert"] {
        border-radius: 8px;
    }
    hr {
        margin: 0.6rem 0;
    }
    div[data-testid="stChatMessage"] {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("💬 AI 수업 활동 에이전트")

ACTIVITIES = ["토의·토론", "Quiz"]
activity = st.radio("Activity 선택", ACTIVITIES, horizontal=True, key="activity")
st.divider()

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


# ============================================================
# 토의·토론 Activity
# ============================================================


def _sync_notion(conv: ConversationState, plan: dict) -> None:
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


def _sync_worksheet_if_needed(conv: ConversationState, old_plan: dict | None, plan: dict) -> None:
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


def _run_generation(conv: ConversationState, revision_request: str | None = None) -> bool:
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
    _sync_notion(conv, plan)
    _sync_worksheet_if_needed(conv, old_plan, plan)
    return True


def _run_worksheet_revision(conv: ConversationState, revision_request: str) -> bool:
    """활동지를 직접 겨냥한 수정 요청을 처리한다. 계획안/Notion은 건드리지 않는다.

    이 함수는 항상 phase를 DRAFTED로 되돌리고 True를 반환해서 호출부가
    바로 rerun한다 — _run_generation()과 달리 이 경로는 phase가 REVISING을
    벗어나는 게 실패 여부와 무관해서(여기서 한 번만 실행되고 다시 자동으로
    트리거되지 않음) 재시도 루프 위험이 없다. 다만 rerun이 바로 따라오므로
    st.error() 같은 일시적 위젯 호출은 화면에 뜨기도 전에 사라진다 —
    성공/실패 메시지 전부 conv.history에 남겨서(대화 기록에 남는 방식으로)
    rerun 이후에도 보이게 한다.
    """
    conv.phase = Phase.DRAFTED
    conv.slots.pop("revision_request", None)

    if not conv.worksheet_doc_id:
        # 예외 상황: 활동지를 아직 안 만들었는데 활동지 수정을 요청한 경우.
        conv.history.append(
            {
                "role": "assistant",
                "content": "아직 학생 활동지를 만들지 않았어요. 먼저 아래 '학생 활동지도 만들기' 버튼으로 만들어주세요.",
            }
        )
        return True

    try:
        with st.spinner("학생 활동지를 수정하는 중..."):
            new_worksheet = generate_worksheet(conv.draft, revision_request=revision_request)
            replace_doc_body(conv.worksheet_doc_id, worksheet_to_text(new_worksheet))
    except WorksheetError as e:
        conv.history.append({"role": "assistant", "content": str(e)})
    except GoogleDocsWriteError as e:
        conv.history.append({"role": "assistant", "content": f"Google Docs 반영에 실패했어요: {e}"})
    except Exception as e:  # noqa: BLE001
        conv.history.append({"role": "assistant", "content": f"활동지 수정 중 문제가 발생했어요: {e}"})
    else:
        conv.worksheet = new_worksheet
        conv.history.append(
            {"role": "assistant", "content": f"학생 활동지를 수정했어요: [{conv.worksheet_url}]({conv.worksheet_url})"}
        )
    return True


def _render_discussion_activity() -> None:
    if "conv" not in st.session_state:
        st.session_state.conv = ConversationState()
        st.session_state.conv.history.append(
            {"role": "assistant", "content": st.session_state.conv.next_question()}
        )
    conv: ConversationState = st.session_state.conv

    st.caption(
        f"과목({', '.join(get_provider().subjects())}), 학년, 주제를 알려주시면 국가교육과정(NCIC) 성취기준에 "
        "근거한 토의·토론 수업계획안을 만들고 Notion에 자동으로 저장해드려요. 생성 후에도 채팅으로 "
        "계속 수정을 요청할 수 있고, 원하면 학생 활동지도 만들어서 Google Docs에 저장할 수 있어요."
    )

    for msg in conv.history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("메시지를 입력하세요", key="discussion_chat_input")
    if user_input:
        with st.chat_message("user"):
            st.write(user_input)
        reply = conv.handle_message(user_input)
        with st.chat_message("assistant"):
            st.write(reply)
        st.rerun()

    # --- READY: 슬롯이 다 채워졌으면 자동으로 생성 트리거 ---
    if conv.phase == Phase.READY:
        if _run_generation(conv):
            st.rerun()

    # --- REVISING: 계획안 수정인지 활동지 수정인지 구분해서 처리 ---
    if conv.phase == Phase.REVISING:
        revision_request = conv.slots.get("revision_request", "")
        target = classify_edit_target(revision_request, has_worksheet=bool(conv.worksheet_doc_id))
        if target == "worksheet":
            if _run_worksheet_revision(conv, revision_request):
                st.rerun()
        elif _run_generation(conv, revision_request=revision_request):
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
            "학생 활동지(Google Docs)에도 자동으로 반영돼요. '활동지 난이도를 낮춰줘'처럼 메시지에 "
            "'활동지'가 들어가면 계획안은 그대로 두고 활동지만 수정해요."
        )


# ============================================================
# Quiz Activity
# ============================================================


def _sync_form(quiz_conv: QuizConversationState, title: str, questions: list[dict]) -> None:
    """퀴즈 문항을 Google Forms에 반영한다. 폼이 없으면 새로 만들고(+게시), 있으면 문항을 통째로 교체한다."""
    try:
        if quiz_conv.form_id:
            with st.spinner("Google Forms 문항을 수정하는 중..."):
                replace_quiz_questions(quiz_conv.form_id, questions)
        else:
            with st.spinner("Google Forms 퀴즈를 만드는 중..."):
                result = create_quiz_form(title, questions)
                quiz_conv.form_id = result["form_id"]
                quiz_conv.edit_url = result["edit_url"]
                quiz_conv.responder_url = result["responder_url"]
    except FormsWriteError as e:
        st.error(f"Google Forms 반영에 실패했어요: {e}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Google Forms 반영 중 문제가 발생했어요: {e}")


def _run_quiz_generation(quiz_conv: QuizConversationState, revision_request: str | None = None) -> bool:
    """퀴즈 문항을 (재)생성하고 Google Forms에 동기화한다. 성공하면 True를 반환한다.

    토의·토론의 _run_generation()과 같은 이유로 실패 시 무조건 rerun하지
    않는다(실패 -> 즉시 rerun -> 재시도 반복 방지, 성공 시 Forms 쓰기까지
    딸려있어 더 위험함).
    """
    slots = quiz_conv.slots
    old_draft = quiz_conv.draft
    try:
        with st.spinner("퀴즈 문항을 만드는 중..."):
            result = generate_quiz(
                subject=slots["subject"],
                topic=slots["topic"],
                grade=slots.get("grade", "고1"),
                revision_request=revision_request,
                current_draft=old_draft,
            )
    except QuizError as e:
        st.error(str(e))
        if old_draft is not None:
            quiz_conv.phase = Phase.DRAFTED
        return False

    quiz_conv.apply_draft(result)
    _sync_form(quiz_conv, f"{result['topic']} 퀴즈", result["questions"])
    return True


def _render_quiz_activity() -> None:
    if "quiz_conv" not in st.session_state:
        st.session_state.quiz_conv = QuizConversationState()
        st.session_state.quiz_conv.history.append(
            {"role": "assistant", "content": st.session_state.quiz_conv.next_question()}
        )
    quiz_conv: QuizConversationState = st.session_state.quiz_conv

    st.caption(
        f"과목({', '.join(get_provider().subjects())}), 학년, 확인하고 싶은 단원/주제를 알려주시면 "
        "객관식 퀴즈(기본 4지선다, 보기 개수는 채팅으로 조정 가능)를 만들고 Google Forms에 "
        "자동으로 저장해드려요(정답 자동 채점 포함). 생성 후에도 채팅으로 계속 수정을 요청할 수 있어요."
    )

    for msg in quiz_conv.history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("메시지를 입력하세요", key="quiz_chat_input")
    if user_input:
        with st.chat_message("user"):
            st.write(user_input)
        reply = quiz_conv.handle_message(user_input)
        with st.chat_message("assistant"):
            st.write(reply)
        st.rerun()

    if quiz_conv.phase == Phase.READY:
        if _run_quiz_generation(quiz_conv):
            st.rerun()

    if quiz_conv.phase == Phase.REVISING:
        if _run_quiz_generation(quiz_conv, revision_request=quiz_conv.slots.get("revision_request")):
            st.rerun()

    if quiz_conv.phase == Phase.DRAFTED and quiz_conv.draft:
        questions = quiz_conv.draft["questions"]
        st.divider()
        st.subheader(f"{quiz_conv.draft.get('topic', '')} — {quiz_conv.draft.get('subject', '')} 퀴즈")

        for i, q in enumerate(questions, start=1):
            with st.expander(f"{i}. {q['question']}", expanded=(i == 1)):
                for j, option in enumerate(q["options"]):
                    marker = "✅" if j == q["correct_index"] else "▫️"
                    st.write(f"{marker} {option}")
                if q.get("explanation"):
                    st.caption(f"해설: {q['explanation']}")

        if quiz_conv.responder_url:
            st.success(f"Google Forms에 반영됨(응답용 링크): [{quiz_conv.responder_url}]({quiz_conv.responder_url})")
            st.caption(f"편집 화면: {quiz_conv.edit_url}")
        else:
            st.warning("아직 Google Forms에 반영되지 않았어요. 위쪽 오류 메시지를 확인해주세요.")

        st.divider()
        if st.button("새로 만들기", key="quiz_reset"):
            quiz_conv.reset()
            quiz_conv.history.append({"role": "assistant", "content": quiz_conv.next_question()})
            st.rerun()

        st.caption(
            "수정하고 싶은 점이 있으면 위 채팅창에 자유롭게 적어주세요 (예: '3번 문제를 더 쉽게 해줘', "
            "'문항을 서술형 대신 계속 객관식으로 늘려줘'). 수정 결과는 같은 Google Forms에 자동으로 반영돼요."
        )


# ============================================================
# Activity 라우팅
# ============================================================

if activity == "토의·토론":
    _render_discussion_activity()
else:
    _render_quiz_activity()
