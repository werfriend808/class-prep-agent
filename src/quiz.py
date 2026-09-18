"""Quiz Activity: 퀴즈 문항 생성 (종합 프로젝트).

lesson_plan.py/worksheet.py와 같은 패턴이다: LLM(llm.complete(), .env의
LLM_PROVIDER를 따름)으로 문항 JSON을 생성한다. 실패 시 한 번 자동 재시도하는
것도 동일(worksheet.py에서 실제로 겪은 클로바 간헐적 형식 오류에 대응하기
위해 lesson_plan.py/worksheet.py에 먼저 붙인 패턴을 그대로 가져왔다).

토의·토론/PBL과 달리 Quiz는 산출물이 하나(퀴즈 문항 → Google Forms)뿐이라
edit_propagation.py 같은 "여러 산출물 중 어디를 고칠지" 판단 로직이 필요
없다 — 수정 요청은 항상 문항 전체를 다시 생성하고 같은 Form에 반영한다.

2026-08-26: 원래 NCIC 근거(ncic_matcher)를 붙였는데, 영어 "문법"처럼 2022
개정 교육과정 성취기준 문구에 아예 안 나오는 주제는 키워드 매칭이 전부 0점이
되고, 그러면 match_standards()가 무관한 성취기준(예: 독해 성취기준)을 그대로
반환해서 프롬프트에 "문법 문제를 내라면서 참고자료는 독해"라는 모순된 지시가
섞여 들어갔다. 실사용 중 이상한 문항이 나오는 걸로 발견됐고(Stanley), NCIC
근거 기능 자체를 제거하기로 결정했다(lesson_plan.py도 동일 구조라 같이 제거
— 자세한 배경은 README 18-6-2 참고).

2026-08-26: 실사용 중 정답 표시 자체가 틀리는 문제가 발견됐다(Stanley) —
예를 들어 "축구에서 득점을 올리는 것을 무엇이라고 부르나요?"라는 문항에서
해설(explanation)은 "'골'이라고 부릅니다"로 정확했는데, 실제 Google Forms에
반영된 정답은 "세이브"였다. 원인은 LLM이 correct_index(0-based 정수)를
셀 때 가끔 실수를 한다는 것으로 보인다 — 같은 문항 안에서 해설 문장은 정답을
말로 정확히 서술하면서도, 그 정답이 options 배열의 몇 번째인지 세는
과정에서만 다른 값을 내놓는 비일관성이었다(JSON 자체는 유효해서 기존
검증(0 <= correct_index < len(options))도 이 오류를 걸러내지 못했다). 인덱스를
세는 것보다 정답 문구를 그대로 옮겨 적는 편이 LLM에게 더 쉬운 작업이라고
보고, LLM에게 요구하는 필드를 correct_index(정수)에서 correct_answer(정답
선택지의 텍스트, options 중 하나와 정확히 일치)로 바꿨다. 파싱 단계
(`_parse_quiz_json`)에서 문자열 일치로 correct_index를 역산하고, 일치하는
보기가 없으면 QuizError를 올려 기존 재시도 정책(1회)이 그대로 작동하게
했다 — options/correct_index 기반의 나머지 코드(forms_writer.py,
chat_app.py)는 그대로 correct_index를 쓰므로 이 변경은 생성 단계에만
국한된다.

2026-08-26 (추가): correct_answer 방식으로 바꾼 뒤에도 Stanley가 실사용
테스트에서 더 넓은 범위의 문제를 발견했다 — ① 문항 문장이 "~는 다음과
같습니다", "~하는 문제입니다"처럼 완결되지 않은 서술형/메타 문장으로 끝나서
무슨 뜻인지 알 수 없거나("다음 중 어류인 생선은 다음과 다르게 생겼습니다"),
심지어 "~을 고르세요"로 시작해놓고 바로 다음 문장에서 "~아닌 것은"으로
뒤집어 자기모순이 되는 경우(246+173 문항), ② 빈칸이 있다면서 정작 그 식
자체가 question 텍스트에서 빠진 경우, ③ 보기 중 계산 결과가 실제로는
동점인데(예: "15+27"와 "30+12"는 둘 다 42, "3x4"와 "4x3"은 둘 다 12) 서로
다른 보기인 것처럼 낸 경우, ④ 정답으로 지목한 값 자체가 실제 계산과 다른
경우(246+173=419인데 correct_answer가 410). 이 중 ①②④는 LLM의 서술/계산
품질 문제라 코드로 완전히 검증할 수 없어서 프롬프트 지시를 구체화해서
줄이는 방식으로 대응했다(_build_prompt() 참고 — 완결된 질문문으로 끝낼 것,
식 자체를 문항에 포함할 것, 부정형 문항은 일관되게 쓸 것, 정답을 정하기
전에 실제로 계산/사실을 확인할 것). ③은 옵션 텍스트가 "숫자 연산자 숫자"
형태의 단순 산술식일 때만 값을 계산해 동점 여부를 기계적으로 검증할 수
있어서(수학 외 과목에는 이 패턴 자체가 안 나오므로 오탐 위험이 낮다)
`_parse_quiz_json`에 `_try_eval_simple_expr()` 기반 검증을 추가했다 —
동점이면 QuizError를 올려 재시도를 유도한다. 보기 텍스트가 완전히 같은
경우(중복 보기)도 과목 무관하게 걸러지도록 별도로 검사한다.

2026-08-26 (추가, 두 번째): 위 대응 이후에도 Stanley가 "'to 부정사'가
형용사적으로 사용되지 않은 것을 고르세요" 같은 영문법 문항에서 더 근본적인
문제를 발견했다 — 보기로 제시된 "happy to see you"/"difficult to
understand"/"easy to learn"이 전부 형용사적 용법이 아니라 부사적 용법인데도
(형용사적 용법은 "a book to read"처럼 to부정사가 명사를 뒤에서 꾸미는 경우다)
문항 자체가 "셋은 형용사적 용법이다"라는 틀린 전제로 만들어졌다. 이건 값이
같은지 계산해서 잡을 수 있는 유형이 아니라 그 과목의 실제 지식(문법 분류가
맞는지)이 있어야 판단 가능해서, `_try_eval_simple_expr()` 같은 기계적 검증으로는
원천적으로 못 잡는다. Stanley가 "크레딧/시간이 더 들어도 검증 LLM 호출을
추가해달라"고 명시적으로 요청해서, `_generate_once()`에 `_verify_questions()`
단계를 추가했다 — 문항을 생성한 것과 같은 LLM에게 결과를 그대로 다시 보여주고
"정답/전제가 실제로 맞는지" 검수시킨다(재작성이 아니라 valid/invalid 판정만).
검수 실패도 QuizError로 처리해서 기존 1회 재시도 정책에 자연스럽게 올라탄다 —
최악의 경우 LLM 호출이 생성 2회+검수 2회로 늘어난다. 검수 호출 자체가
실패하거나(네트워크 등) 검수 응답 형식이 깨지면 조용히 건너뛴다(원 결과를
그대로 씀) — 검수는 있으면 좋은 안전장치지 필수 관문이 아니라고 판단했다.
자세한 배경은 README 18-6-5 참고.

2026-08-26 (추가, 세 번째): 검증 LLM 호출을 추가한 직후, Stanley가 영어
과목 "to부정사" 단원 퀴즈를 생성하다가 "3번 문항의 정답(correct_answer)이
보기 중에 없어요"라는 오류를 다시 겪었다(재시도 1회까지 소진하고도 실패).
실제 원문 응답을 직접 확인하지는 못했지만, 영어 지문이라는 점에서 LLM이
정답 문구를 옮겨 적을 때 따옴표를 붙이거나(예: '"interested in playing"'),
대소문자를 바꾸거나, 끝에 마침표를 붙이는 등 options 배열의 원문과 완전히
동일하지 않게 재서술했을 가능성이 높다고 보고(가설이며 확정 원인은 아님),
`_parse_quiz_json`의 correct_answer 매칭 로직을 2단계로 강화했다 — ① 기존과
동일하게 완전 일치를 먼저 시도하고, ② 실패하면 `_normalize_for_match()`로
양쪽을 정규화(따옴표/문장부호 제거, 소문자 변환)한 뒤 정확히 하나의 보기와만
일치하는 경우에만 그 보기를 정답으로 채택한다. 정규화 후에도 일치하는 보기가
없거나 둘 이상이면(모호함) 여전히 QuizError를 올려 기존 재시도 정책을 그대로
따른다 — 즉 이 완화는 "명백히 같은 답을 다르게 표기한 경우"만 구제하고,
실제로 다른 답이거나 모호한 경우는 이전과 동일하게 거른다.

2026-08-26 (추가, 네 번째): Stanley가 수학 퀴즈를 Google Forms에서 확인하다가
해설(explanation)에 "전체 imesrac{30}{100}=12"처럼 알아볼 수 없는 텍스트가
섞여 나오는 걸 발견했다. \times/\frac{}{} 같은 LaTeX 표기가 원인으로 보인다 —
LLM이 explanation을 JSON으로 낼 때 백슬래시를 이스케이프하지 않고 그대로 쓰면(예:
"\times"), JSON 표준상 "\t"와 "\f"는 그 자체로 유효한 이스케이프(각각 탭,
폼피드)라서 json.loads()가 예외 없이 통과시키면서 "\times"는 탭+"imes"로,
"\frac"는 폼피드+"rac"로 조용히 망가진다 — JSON 자체는 유효하므로 기존 파싱
예외 처리로는 못 잡는다. 두 가지로 대응했다 — ① `_build_prompt()`에 규칙 (5)를
추가해 LaTeX/마크다운 수식 표기를 쓰지 말고 ×, ÷, / 같은 일반 기호로만 쓰라고
명시했다(근본 원인 예방, 프롬프트만으로는 100% 보장 못함). ② 이미 손상된 경우를
잡아내는 안전망으로 `_UNEXPECTED_CONTROL_CHAR_RE`를 추가했다 — question/options/
explanation에 줄바꿈(\n) 외의 제어문자가 하나라도 남아있으면(탭·폼피드 등) 이
손상 패턴으로 보고 QuizError를 올려 재시도를 유도한다(제어문자가 사라진 시점엔
원래 LaTeX 표기를 복원할 방법이 없어 고쳐 쓰지 않고 다시 생성하게 한다). 자세한
배경은 README 18-6-7 참고.

2026-08-26 (추가, 다섯 번째): Stanley가 수학 퀴즈에서 "다음은 어느 학급에서
조사한 일주일 동안 읽은 책의 수를 나타낸 상대도입니다"로 시작하는 문항을 발견하고
지적했다 — Quiz는 텍스트만 Google Forms에 반영하고 그래프/표/그림을 별도로 만들어
붙이는 기능 자체가 없는데, 문항이 학생은 볼 수 없는 상대도(그래프)가 어딘가에
있다는 전제로 만들어져서 원천적으로 풀 수 없는 문항이 됐다. `_build_prompt()`에
규칙 (6)을 추가해 시각 자료를 참조하지 말고 필요한 데이터를 문항 문장 안에 직접
숫자/텍스트로 다 적으라고 지시했고(근본 원인 예방), 흔히 쓰이는 참조 표현("다음
그래프를 보고", "~을 나타낸 표입니다" 등)을 감지하는 `_VISUAL_REFERENCE_RE`를
안전망으로 추가해 여전히 이런 문항이 나오면 QuizError로 재시도를 유도한다. 자세한
배경은 README 18-6-8 참고.
"""
from __future__ import annotations

import json
import re

from .llm import complete

QUESTION_COUNT = 5
MIN_OPTIONS = 2
MAX_OPTIONS = 6
DEFAULT_OPTION_COUNT = 4

# "숫자 연산자 숫자" 형태의 단순 산술식만 매칭한다(예: "15+27", "3 x 4", "7÷2").
# 문장이 섞인 보기(예: "칠 곱하기 팔은 오십육")나 결과값만 있는 보기(예: "419")는
# 매칭되지 않으므로, 수학이 아닌 과목이나 결과값 자체를 고르는 문항에는 아래
# 동점 검증이 아예 적용되지 않는다(오탐 방지를 위해 의도적으로 엄격하게 좁혔다).
_SIMPLE_EXPR_RE = re.compile(r"^(\d+)\s*([+\-x×*÷/])\s*(\d+)$")

# correct_answer 정규화용 문자 집합(곧은/굽은 따옴표 + 마침표/쉼표) — 소스에서
# 따옴표를 중첩해서 쓰지 않도록 chr()로 조합한다.
_QUOTE_AND_PUNCT_CHARS = (
    chr(39) + chr(34)  # ' "
    + chr(0x2018) + chr(0x2019)  # ' '
    + chr(0x201C) + chr(0x201D)  # " "
    + ".,"
)


def _normalize_for_match(text: str) -> str:
    """correct_answer를 options와 비교할 때 쓰는 관대한 정규화. 2026-08-26 —
    영어 문항에서 "3번 문항의 정답(correct_answer)이 보기 중에 없어요"가 반복
    발생했다(Stanley 실사용 보고). LLM이 정답 자체는 제대로 골랐는데도 보기를
    그대로 베끼지 않고 따옴표를 둘러싸거나("interested in playing" 대신
    'interested in playing'), 끝에 마침표를 붙이거나, 대소문자를 바꿔 적는 등
    사소하게 다르게 옮겨 적는 경우가 있었던 것으로 보인다. 완전 일치 비교가
    이런 사소한 차이까지 실패로 처리해서 멀쩡한 정답도 재시도를 태우고 있었을
    가능성이 있어, 양쪽 끝의 따옴표·마침표를 떼고 대소문자를 무시하는 비교를
    폴백으로 추가했다 — 내용이 실제로 다른 오답까지 관대해지는 게 아니라,
    "같은 텍스트를 표기만 다르게 적은" 경우만 구제한다."""
    return text.strip().strip(_QUOTE_AND_PUNCT_CHARS).strip().lower()


# JSON 문자열 안에 LaTeX 표기(예: "\times", "\frac{30}{100}")가 이스케이프
# 없이 그대로 들어오면, "\t"/"\f"/"\r" 등 JSON 표준 이스케이프와 우연히
# 겹치는 부분만 json.loads()가 조용히 제어문자로 바꿔버리고 나머지 글자는 그대로
# 남는다(예: "\times" -> 탭 + "imes", "\frac" -> 폼피드 + "rac") — 결과 JSON
# 자체는 유효해서 파싱 예외로는 못 잡는다(2026-08-26, README 18-6-7 참고). 문항
# 텍스트에 정상적으로 나올 이유가 없는 제어문자이므로, 줄바꿈(\n)만 허용하고
# 나머지 제어문자가 하나라도 섞여 있으면 이 손상 패턴으로 간주해 재시도를 유도한다.
_UNEXPECTED_CONTROL_CHAR_RE = re.compile(r"[\x00-\x09\x0b-\x1f]")


# Quiz는 텍스트만 Google Forms에 반영하고 이미지/그래프/표를 별도로 만들어
# 첨부하지 않는다(그런 기능 자체가 없다). 그런데도 LLM이 "다음 그래프를 보고",
# "다음은 ~을 나타낸 상대도입니다"처럼 문항 밖에 시각 자료가 있다는 전제로 문항을
# 내는 경우가 실사용 중 발견됐다(2026-08-26, Stanley 실사용 보고, README 18-6-8
# 참고) — 학생 입장에서는 참조된 그래프/표가 어디에도 없어서 풀 수 없는 문항이
# 된다. _build_prompt()의 규칙 (6)으로 이런 문항을 내지 말라고 지시했지만 100%
# 지켜진다는 보장이 없어서, 흔히 쓰이는 참조 표현을 기계적으로 감지해 걸러내는
# 안전망을 추가한다(값이 맞는지 판단하는 게 아니라 특정 표현 패턴만 찾는 순수
# 문자열 매칭이라 오탐 위험이 낮다).
_VISUAL_REFERENCE_RE = re.compile(
    r"(다음|위|아래)\s*(그림|사진|지도|그래프|도표|차트|표|상대도)(을|를)?\s*(보고|참고|참고하여|보면)"
    r"|나타낸\s*(그래프|표|도표|차트|그림|사진|지도|상대도)"
)


def _try_eval_simple_expr(text: str) -> float | None:
    """"3x4" 같은 단순 두 항 산술식 문자열을 계산한다. 매칭되지 않거나 0으로
    나누면 None을 반환한다(동점 검증에서 이 문항은 건너뛴다는 뜻)."""
    m = _SIMPLE_EXPR_RE.match(text)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op in ("x", "×", "*"):
        return a * b
    if op in ("÷", "/"):
        return a / b if b != 0 else None
    return None


class QuizError(RuntimeError):
    """퀴즈 생성 실패(크레딧 부족, 응답 파싱/검증 실패 등)를 UI에 알리기 위한 예외."""


def _build_prompt(
    subject: str,
    grade: str,
    topic: str,
    revision_request: str | None,
    current_questions: list[dict] | None = None,
) -> str:
    if revision_request and current_questions:
        # 수정 요청이 "1번 문항 보기를 3개로 줄여줘"처럼 특정 문항을 지목할 수 있는데,
        # 기존에는 현재 문항 내용을 프롬프트에 전혀 안 넘기고 매번 백지에서 5개를 새로
        # 만들었다 — "1번 문항"이 뭔지 LLM이 알 방법이 없어 요청과 무관한 다른 문항까지
        # 같이 흔들리는 문제가 실사용 중 발견됐다(2026-08-26). 현재 문항을 그대로 보여주고
        # 그걸 기준으로 고치라고 지시해서 지목형 수정 요청이 안정적으로 반영되게 한다.
        current_text = "\n".join(
            f"{i + 1}. {q['question']}\n"
            + "\n".join(
                f"   {chr(97 + j)}) {opt}" + (" [정답]" if j == q.get("correct_index") else "")
                for j, opt in enumerate(q.get("options", []))
            )
            for i, q in enumerate(current_questions)
        )
        revision_note = (
            f"\n\n[현재 문항]\n{current_text}\n\n"
            f"[수정 요청]\n위 현재 문항을 기준으로 다음 피드백을 반영해서 문항 전체를 "
            f"다시 작성해주세요(요청에서 언급하지 않은 문항이나 보기는 가능한 한 원래 "
            f"내용을 그대로 유지하세요): {revision_request}"
        )
    elif revision_request:
        revision_note = (
            f"\n\n[수정 요청]\n이전 문항에 대해 다음 피드백을 반영해서 다시 작성해주세요: {revision_request}"
        )
    else:
        revision_note = ""
    return (
        f"당신은 {grade} {subject} 교사를 돕는 평가 문항 출제 도우미입니다. "
        f"아래 단원/주제에 대한 이해도를 확인하는 객관식 퀴즈를 만들어주세요.\n\n"
        f"단원/주제: {topic}\n\n"
        f"정확히 {QUESTION_COUNT}개의 문항을 담은 JSON 객체로만 답하세요 (다른 설명 없이 JSON만): "
        '{"questions": [{"question": "문항 텍스트", '
        '"options": ["선택지1", "선택지2", "선택지3", "선택지4"], '
        '"correct_answer": "정답 선택지의 텍스트 (options 중 하나와 완전히 동일한 문자열이어야 함, 인덱스 아님)", '
        '"explanation": "정답 해설"}, ...]}. '
        f"options 개수는 보기를 늘리거나 줄여달라는 별도 요청이 없으면 기본 {DEFAULT_OPTION_COUNT}개로 하고, "
        f"보기 개수 조정을 원한다는 내용이 있으면 그에 맞게 조정하되 "
        f"{MIN_OPTIONS}개 이상 {MAX_OPTIONS}개 이하로만 작성하세요. 각 문항의 options는 "
        f"서로 명확히 구분되게 작성하고, 정답은 하나만 있어야 합니다. correct_answer는 반드시 "
        f"options 목록에 있는 문자열 중 하나를 그대로 옮겨 적으세요(번호나 순서를 세지 말고 "
        f"정답 선택지의 실제 텍스트를 적으세요). "
        f"다음 규칙도 반드시 지키세요: "
        f"(1) question은 그 자체로 완결된 질문문이나 지시문으로 끝나야 합니다(예: '~은 무엇입니까?', "
        f"'~을 고르세요', '~인가요? 예/아니오로 답하세요'). '~는 다음과 같습니다', '~하는 문제입니다' 같은 "
        f"서술형·메타적인 문장으로 문항을 끝내지 마세요. "
        f"(2) 계산식이나 수식이 필요한 문항이라면 그 식 자체를 question 안에 명확히 포함하세요(예: "
        f"'246 + 173 = ?'). 식이 있다는 사실만 언급하고 실제 식을 빠뜨리지 마세요. "
        f"(3) '~이 아닌 것은?'처럼 부정형으로 묻는 문항은 문항 전체를 부정형으로 일관되게 쓰세요 — "
        f"긍정형 표현과 부정형 표현을 한 문항 안에서 섞지 마세요. "
        f"(4) correct_answer를 정하기 전에 실제로 계산하거나 사실을 확인해서, 정답이 명확히 하나뿐이고 "
        f"나머지 오답들과 값·의미가 겹치지 않는지 확인하세요(특히 숫자를 순서만 바꾼 식이 실제로는 "
        f"같은 값이 되지 않는지 검산하세요). "
        f"(5) 수식은 LaTeX나 마크다운 문법(예: \\times, \\frac{{}}{{}}, \\sqrt{{}}, \\div, \\cdot, $...$) "
        f"없이 일반 텍스트로만 쓰세요 — 결과물은 서식이 적용되지 않는 일반 텍스트로 표시됩니다. "
        f"곱하기는 '×'나 'x', 나누기는 '÷'나 '/', 분수는 '30/100'처럼 일반 슬래시로 쓰세요. "
        f"(6) 이 퀴즈는 텍스트만 표시되고 이미지·그래프·표·도표를 별도로 첨부하지 않습니다 — "
        f"'다음 그래프를 보고', '위 표를 참고하여', '다음은 ~을 나타낸 그래프입니다'처럼 문항 밖에 "
        f"별도의 시각 자료가 있다고 전제하는 문항은 절대 내지 마세요. 표나 그래프로 보여줄 법한 데이터가 "
        f"필요한 문항이라면, 그 데이터를 문항 문장 안에 직접 숫자/텍스트로 다 적어서(예: '어느 반의 요일별 "
        f"독서량은 월 8권, 화 12권, 수 10권, 목 6권, 금 4권입니다.') 문항만 읽어도 그림 없이 풀 수 있게 "
        f"만드세요."
        f"{revision_note}"
    )


def _build_verification_prompt(subject: str, grade: str, topic: str, questions: list[dict]) -> str:
    """생성된 문항을 그대로 되짚어 보여주고 LLM에게 검수를 시키는 프롬프트를 만든다.

    2026-08-26: 프롬프트/코드 검증(중복 보기, 산술식 동점 등)을 다 추가했는데도
    Stanley가 실사용 중 더 근본적인 문제를 발견했다 — 예를 들어 "'to 부정사'가
    형용사적으로 사용되지 않은 것을 고르세요" 문항에서, 보기로 든 "happy to see
    you"/"difficult to understand"/"easy to learn"는 사실 셋 다 형용사적 용법이
    아니라 부사적 용법인데도(형용사적 용법은 "a book to read"처럼 to부정사가
    명사를 뒤에서 꾸미는 경우다) 문항 자체가 "셋은 형용사적 용법이고 하나만
    아니다"라는 잘못된 전제로 만들어졌다. 이런 오류는 값이 같은지 계산하는 걸로는
    못 잡고, 그 과목의 실제 지식이 있어야 판단할 수 있어서 별도의 LLM 검수
    호출을 추가했다 — 문항을 생성한 것과 같은 LLM에게 결과물을 다시 보여주고
    "실제로 맞는지" 검산하게 한다(재작성이 아니라 valid/invalid 판정만 시킨다)."""
    numbered = "\n\n".join(
        f"{i + 1}. {q['question']}\n"
        + "\n".join(
            f"   {chr(97 + j)}) {opt}" + (" [표시된 정답]" if j == q["correct_index"] else "")
            for j, opt in enumerate(q["options"])
        )
        + f"\n   해설: {q.get('explanation', '')}"
        for i, q in enumerate(questions)
    )
    return (
        f"당신은 {grade} {subject} 과목의 검수 담당 교사입니다. 아래는 '{topic}' 주제로 만들어진 "
        f"객관식 퀴즈 문항들이고, 각 문항에서 [표시된 정답]이라고 표시된 보기가 그 문항의 정답으로 "
        f"채점됩니다. 각 문항을 실제로 계산하거나 개념/문법을 확인해서, 아래 기준으로 하나씩 "
        f"검수해주세요:\n"
        f"(1) [표시된 정답]이 실제로 맞는 답인가?\n"
        f"(2) 정답이 하나로 명확히 좁혀지는가(다른 보기도 정답이 될 수 있지는 않은가)?\n"
        f"(3) 문항이 전제하는 개념/분류/문법 설명 자체가 정확한가(예: 보기들을 특정 문법 범주나 "
        f"개념으로 분류하는 문항이라면, 그 분류가 실제로 맞는가)?\n"
        f"(4) 문항 텍스트가 그 자체로 완결되고 명확한 질문인가(필요한 식이나 정보가 빠지지 "
        f"않았는가)?\n\n"
        f"[문항]\n{numbered}\n\n"
        f"다음 JSON 형식으로만 답하세요 (다른 설명 없이 JSON만): "
        '{"results": [{"valid": true 또는 false, "reason": "valid가 false일 때만 위 (1)~(4) 중 '
        '어떤 기준을 왜 어겼는지 한 문장으로"}, ...]}. '
        f"results 배열은 반드시 {len(questions)}개여야 하고, 위 문항 순서와 정확히 일치해야 합니다."
    )


def _parse_verification_json(raw_text: str, expected_count: int) -> list[dict] | None:
    """검수 응답을 파싱한다. 형식이 이상하면(다른 검증들과 달리) 예외를 올리지
    않고 None을 반환한다 — 검수는 있으면 좋은 안전장치일 뿐 필수 관문이 아니라서,
    검수 응답 자체가 깨졌다고 정상적으로 만들어진 퀴즈까지 버리지 않기 위함이다."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or len(results) != expected_count:
        return None
    return results


def _verify_questions(subject: str, grade: str, topic: str, questions: list[dict]) -> None:
    """문항들을 LLM에게 다시 검수시킨다. 하나라도 invalid 판정을 받으면 QuizError를
    올려서 _generate_once()를 호출하는 쪽의 기존 1회 재시도 정책이 검수 실패에도
    똑같이 작동하게 한다(형식 오류든 검수 실패든 "다시 한 번 만들어본다"는 대응은
    동일하다는 판단). 검수 호출 자체가 실패하거나(네트워크/크레딧 등) 검수 응답
    형식이 깨지면 조용히 건너뛴다 — 검수 인프라 문제 때문에 정상적으로 만들어진
    퀴즈까지 버리지 않기 위함이다."""
    prompt = _build_verification_prompt(subject, grade, topic, questions)
    try:
        raw_text = complete(prompt, max_tokens=1500)
    except Exception:  # noqa: BLE001 — 검수 호출 실패는 원 결과를 그대로 쓰고 넘어간다
        return
    verdicts = _parse_verification_json(raw_text, len(questions))
    if verdicts is None:
        return
    invalid = [v for v in verdicts if not v.get("valid", True)]
    if invalid:
        reasons = " / ".join(str(v.get("reason", "")).strip() for v in invalid if v.get("reason"))
        raise QuizError(f"문항 검수에서 문제가 발견됐어요: {reasons or '정답/전제가 정확하지 않은 문항이 있어요.'}")


def _generate_once(subject: str, grade: str, topic: str, prompt: str) -> dict:
    try:
        raw_text = complete(prompt, max_tokens=2000)
    except Exception as e:  # noqa: BLE001 — 크레딧 부족, 네트워크 오류 등 예상 밖 오류 포함
        raise QuizError(f"퀴즈 생성에 실패했어요 (LLM 호출 오류): {e}") from e
    result = _parse_quiz_json(raw_text)
    _verify_questions(subject, grade, topic, result["questions"])
    return result


def generate_quiz(
    subject: str,
    topic: str,
    grade: str = "고1",
    revision_request: str | None = None,
    current_draft: dict | None = None,
) -> dict:
    """단원/주제에 대한 객관식 퀴즈를 생성한다.

    반환값: {"questions": [...], "subject", "grade", "topic"}.
    각 question은 {"question", "options"(기본 4개, 요청에 따라 2~6개), "correct_index", "explanation"}.
    실패 시(크레딧 부족, JSON 파싱/검증 실패, 아래 검수 실패 등) QuizError를
    올린다. LLM이 가끔 형식 지시를 안 지키는 간헐적 현상에 대응해 실패하면
    한 번만 자동 재시도하고, 그래도 실패하면 그대로 올린다(lesson_plan.py/
    worksheet.py와 동일한 정책).

    2026-08-26 (추가): 문항을 파싱한 뒤 같은 LLM에게 결과를 다시 보여주고
    "정답/전제가 실제로 맞는지" 검수시키는 단계(_verify_questions())를
    _generate_once() 안에 추가했다 — 코드로는 잡을 수 없는 유형의 오류(계산을
    아예 틀리고 확신하거나, 문법/개념 분류 자체가 틀린 경우, 18-6-5 참고)를
    줄이기 위함이다. 검수도 형식 오류와 똑같이 QuizError로 실패하므로 위 1회
    재시도가 검수 실패에도 그대로 적용된다 — 즉 최악의 경우 LLM 호출이
    생성 2회 + 검수 2회로 늘어난다(기존엔 생성만 최대 2회). 크레딧/시간이
    더 드는 트레이드오프를 Stanley가 인지하고 명시적으로 요청해서 추가했다.
    """
    current_questions = current_draft.get("questions") if current_draft else None

    prompt = _build_prompt(subject, grade, topic, revision_request, current_questions)

    try:
        result = _generate_once(subject, grade, topic, prompt)
    except QuizError:
        result = _generate_once(subject, grade, topic, prompt)

    result["subject"] = subject
    result["grade"] = grade
    result["topic"] = topic
    return result


def _parse_quiz_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise QuizError("LLM 응답을 퀴즈 형식으로 해석하지 못했어요. 다시 시도해주세요.") from e

    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list) or not questions:
        raise QuizError("LLM 응답에 문항(questions) 목록이 없어요. 다시 시도해주세요.")

    validated: list[dict] = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise QuizError(f"{i + 1}번 문항 형식이 올바르지 않아요.")
        options = q.get("options")
        if not isinstance(options, list) or not (MIN_OPTIONS <= len(options) <= MAX_OPTIONS):
            raise QuizError(
                f"{i + 1}번 문항의 선택지 개수가 올바르지 않아요 "
                f"({MIN_OPTIONS}개 이상 {MAX_OPTIONS}개 이하여야 해요)."
            )
        stripped_options = [str(o).strip() for o in options]
        if len(set(stripped_options)) != len(stripped_options):
            # 과목/문항 유형과 무관하게 보기 텍스트가 완전히 겹치면 무조건 잘못된
            # 문항이다 — 재시도를 유도한다.
            raise QuizError(f"{i + 1}번 문항의 보기 중 내용이 겹치는 것이 있어요. 다시 시도해주세요.")
        evaluated = [_try_eval_simple_expr(opt) for opt in stripped_options]
        if all(v is not None for v in evaluated) and len(set(evaluated)) != len(evaluated):
            # 보기 전부가 "숫자 연산자 숫자" 형태의 단순 산술식일 때만 도달한다(수학 외
            # 과목/결과값을 고르는 문항에는 이 패턴 자체가 안 나온다). 순서만 바꾼
            # 식(예: "15+27"과 "30+12")이 실제로는 같은 값이라 정답이 여러 개가 되는
            # 문제가 실사용 중 반복적으로 발견됐다(quiz.py 모듈 docstring 참고).
            raise QuizError(
                f"{i + 1}번 문항의 보기 중 계산 결과가 같은 것이 있어요(예: 순서만 바꾼 식). 다시 시도해주세요."
            )
        correct_answer = q.get("correct_answer")
        if not isinstance(correct_answer, str) or not correct_answer.strip():
            raise QuizError(f"{i + 1}번 문항에 정답(correct_answer)이 없어요.")
        correct_answer_stripped = correct_answer.strip()
        if correct_answer_stripped in stripped_options:
            correct_index = stripped_options.index(correct_answer_stripped)
        else:
            # 완전 일치가 안 되면, 따옴표/마침표/대소문자 차이만 있는 경우를
            # 구제하는 관대한 매칭을 한 번 더 시도한다(_normalize_for_match 참고,
            # 2026-08-26 — 영어 문항에서 이 에러가 반복 발생해서 추가). 정규화 후에도
            # 정확히 하나의 보기에만 매칭돼야 인정한다 — 둘 이상이 매칭되면(모호함)
            # 어느 쪽인지 확신할 수 없으므로 그대로 실패 처리한다.
            normalized_answer = _normalize_for_match(correct_answer_stripped)
            fuzzy_matches = [
                idx for idx, opt in enumerate(stripped_options)
                if _normalize_for_match(opt) == normalized_answer
            ]
            if len(fuzzy_matches) == 1:
                correct_index = fuzzy_matches[0]
            else:
                # LLM이 정답 텍스트를 보기 중 하나와 다르게(완전히 다른 재서술 등) 적은
                # 경우 — 인덱스를 역산할 방법이 없으므로 재시도를 유도한다(quiz.py의
                # 기존 1회 재시도 정책, generate_quiz 참고).
                raise QuizError(f"{i + 1}번 문항의 정답(correct_answer)이 보기 중에 없어요.")
        question_text = str(q.get("question", "")).strip()
        if not question_text:
            raise QuizError(f"{i + 1}번 문항에 문제 텍스트가 없어요.")
        explanation_text = str(q.get("explanation", "")).strip()
        if any(
            _UNEXPECTED_CONTROL_CHAR_RE.search(t)
            for t in (question_text, explanation_text, *stripped_options)
        ):
            # LaTeX 표기가 JSON 이스케이프와 충돌해 손상된 패턴으로 보인다
            # (_UNEXPECTED_CONTROL_CHAR_RE 정의부 주석, README 18-6-7 참고) — 재시도를
            # 유도한다. 이스케이프 자체는 이미 사라진 뒤라 원래 표기를 복원할 방법이
            # 없으므로 여기서 고쳐 쓰지 않고 다시 생성하게 한다.
            raise QuizError(
                f"{i + 1}번 문항에 깨진 특수문자(표시되지 않는 제어문자)가 섞여 있어요. "
                "다시 시도해주세요."
            )
        if _VISUAL_REFERENCE_RE.search(question_text) or _VISUAL_REFERENCE_RE.search(explanation_text):
            # Quiz는 텍스트만 Forms에 반영하고 그래프/표/그림을 별도로 만들어 붙이지
            # 않는다(_VISUAL_REFERENCE_RE 정의부 주석, README 18-6-8 참고) — 이런 표현이
            # 있으면 문항 밖에 학생이 볼 수 없는 자료가 있다는 뜻이라 재시도를 유도한다.
            raise QuizError(
                f"{i + 1}번 문항이 이 퀴즈에 없는 그래프/표/그림을 참조하고 있어요. "
                "다시 시도해주세요."
            )
        validated.append(
            {
                "question": question_text,
                "options": stripped_options,
                "correct_index": correct_index,
                "explanation": explanation_text,
            }
        )

    return {"questions": validated}
