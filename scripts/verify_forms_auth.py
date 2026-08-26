"""Google Forms REST API 연동(forms_writer.py) 수동 검증 스크립트.

google_docs_writer.py와 같은 OAuth 인증(get_credentials(), token.json 캐시)을
그대로 재사용하므로, verify_google_docs_auth.py를 이미 성공적으로 실행해
token.json이 있다면 이 스크립트는 브라우저 없이 바로 실행된다. 아직 한 번도
인증한 적이 없다면 이번에도 브라우저가 자동으로 열린다.

실행 전 준비:
    - credentials.json이 프로젝트 루트에 있어야 함 (Docs 검증과 동일한 파일)
    - Google Cloud Console에서 이 프로젝트에 Forms API
      (forms.googleapis.com)가 사용 설정(Enable)되어 있어야 함 — Docs/Drive API를
      켰던 것과 같은 화면(APIs & Services > Library)에서 "Google Forms API"를
      검색해서 켜주면 된다. 꺼져 있으면 아래 실행 시 403 오류가 난다.

실행:
    python scripts/verify_forms_auth.py

성공하면 출력된 편집 화면(edit_url)을 열어서 문항 4개가 잘 들어갔는지,
정답으로 표시한 선택지에 실제로 정답 체크가 되어 있는지 확인하고, 응답용
링크(responder_url)를 열어서 바로 응답을 제출할 수 있는 상태인지(게시가
잘 됐는지) 확인해주세요.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.forms_writer import FormsWriteError, create_quiz_form  # noqa: E402

TEST_TITLE = "[검증용] class-prep-agent Google Forms 연동 테스트"
TEST_QUESTIONS = [
    {
        "question": "삼각형의 내각의 합은?",
        "options": ["90도", "180도", "270도", "360도"],
        "correct_index": 1,
        "explanation": "삼각형의 세 내각의 합은 항상 180도입니다.",
    },
    {
        "question": "이 문서는 무엇을 검증하기 위해 만들어졌나요?",
        "options": [
            "Notion 연동",
            "Google Docs 연동",
            "Google Forms 연동(OAuth 인증 + 문항 생성 + 게시)",
            "이메일 발송",
        ],
        "correct_index": 2,
        "explanation": "forms_writer.py의 create_quiz_form()이 실제로 동작하는지 확인하는 스크립트입니다.",
    },
]


def main() -> None:
    print("Google 인증을 시작합니다. 브라우저가 열리지 않으면 터미널에 출력되는 URL을 직접 열어주세요...")
    try:
        result = create_quiz_form(TEST_TITLE, TEST_QUESTIONS)
    except FormsWriteError as exc:
        print(f"실패: {exc}")
        print(
            "\nForms API가 아직 이 GCP 프로젝트에서 사용 설정되지 않았을 수 있습니다. "
            "Google Cloud Console > APIs & Services > Library에서 'Google Forms API'를 "
            "검색해서 사용 설정한 뒤 다시 시도해주세요."
        )
        raise SystemExit(1) from exc

    print("성공!")
    print("form_id:", result["form_id"])
    print("edit_url (문항 편집 화면):", result["edit_url"])
    print("responder_url (학생 응답 화면):", result["responder_url"])
    print("\n위 edit_url을 열어서 문항 2개와 정답 체크가 잘 들어갔는지 눈으로 확인해주세요.")
    print("responder_url을 열어서 실제로 응답을 제출할 수 있는지(게시 상태)도 확인해주세요.")


if __name__ == "__main__":
    main()
