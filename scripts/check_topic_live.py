"""과목·학년·주제 정합성 판정(src/topic_check.py)을 실제 LLM으로 돌려보는 수동 검증 스크립트.

단위 테스트(tests/test_topic_check.py 등)는 LLM 판정을 가짜 응답으로 바꿔서 "어떤
판정이 오면 우리가 올바르게 처리하는가"만 확인한다. LLM이 실제로 맞게 판정하는지는
이 스크립트로 직접 돌려봐야 알 수 있다 — 결과는 실행할 때마다 달라질 수 있으니, 몇 번
돌렸고 몇 개가 기대와 맞았는지를 그대로 기록하는 용도로 쓴다.

실행 (저장소 루트에서, .env의 LLM 설정을 그대로 쓴다 — 호출 비용이 나간다):
    python scripts/check_topic_live.py             # 판정만 (케이스당 LLM 0~1회)
    python scripts/check_topic_live.py --generate  # 판정 후 Quiz 생성까지 (케이스당 최대 +4회)

사용 지표(Supabase)에는 아무것도 기록하지 않는다 — 검증 실행이 실제 사용량 지표에
섞이지 않게 usage.sink를 끈다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.llm as llm  # noqa: E402
import src.topic_check as topic_check  # noqa: E402
import src.usage as usage  # noqa: E402
from src.errors import GenerationError  # noqa: E402
from src.quiz import generate_quiz  # noqa: E402

# (과목, 학년, 주제, locale, 기대 판정 집합, 메모)
CASES = [
    ("수학", "초1", "이차함수", "ko", {"other_grade"}, "중3/고1 쪽"),
    ("영어", "고1", "고전시가", "ko", {"other_subject"}, "국어"),
    ("영어", "고1", "문법", "ko", {"too_broad"}, "좁힌 주제 제시"),
    ("도덕", "중2", "성선설 성악설", "ko", {"other_grade"}, "고등 윤리 쪽"),
    ("국어", "고1", "고전시가", "ko", {"ok_unmatched"}, "막히면 안 됨"),
    ("수학", "중3", "이차함수", "ko", {"ok"}, "LLM 호출 없음"),
    ("영어", "고1", "관계대명사 who/which", "ko", {"ok", "ok_unmatched"}, "막히면 안 됨"),
    ("Math", "1", "quadratic functions", "us", {"other_grade"}, "Grade 9"),
]


class _CallCounter:
    def __init__(self, inner):
        self.inner, self.count = inner, 0

    def __call__(self, prompt, max_tokens=1000):
        self.count += 1
        return self.inner(prompt, max_tokens=max_tokens)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="판정을 통과하면 Quiz 생성까지 실행")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글/기호 출력
    usage.sink = lambda row: None

    matched = 0
    for subject, grade, topic, locale, expected, note in CASES:
        counter = _CallCounter(llm.complete)
        topic_check.complete = counter
        print("=" * 72)
        print(f"[{locale}] {subject} / {grade} / {topic}    기대: {' 또는 '.join(sorted(expected))} ({note})")
        try:
            check = topic_check.check_topic(subject, grade, topic, locale=locale)
        except Exception as e:  # noqa: BLE001
            print(f"  판정 실패: {type(e).__name__}: {e}")
            continue
        print(f"  판정: {check.status}   LLM 호출: {counter.count}회")
        print(f"  추천 학년: {check.suggested_grade}   추천 과목: {check.suggested_subject}")
        print(f"  좁힌 주제: {check.narrower_topics}")
        print(f"  성취기준: {len(check.standards)}건   다른 위치: "
              f"{[(loc['subject'], loc['grade_group'], loc['count']) for loc in check.locations]}")
        if check.llm_raw is not None:
            print(f"  LLM 원문 응답: {check.llm_raw.strip()}")
        if check.needs_clarification:
            print("  화면 문구:")
            for line in topic_check.format_message(check, locale).splitlines():
                print(f"    {line}")
        hit = check.status in expected
        matched += hit
        print(f"  기대와 일치: {'예' if hit else '아니오'}")

        if args.generate and not check.needs_clarification:
            quiz_counter = _CallCounter(llm.complete)
            import src.quiz as quiz_module

            quiz_module.complete = quiz_counter
            try:
                result = generate_quiz(subject, topic, grade=grade, locale=locale)
                print(f"  Quiz 생성 성공: {len(result['questions'])}문항, LLM 호출 {quiz_counter.count}회")
            except GenerationError as e:
                print(f"  Quiz 생성 실패 (LLM 호출 {quiz_counter.count}회)")
                print(f"    화면 문구: {e.user_message}")
                print(f"    내부 사유: {e}")
    print("=" * 72)
    print(f"기대 판정과 일치한 케이스: {matched}/{len(CASES)}  (이번 1회 실행 결과)")


if __name__ == "__main__":
    main()
