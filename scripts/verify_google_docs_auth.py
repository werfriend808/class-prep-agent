"""Google Docs REST API 연동(google_docs_writer.py) 수동 검증 스크립트.

최초 실행 시 브라우저가 자동으로 열리면서 Google 로그인 + 동의 화면이 뜬다.
동의하면 token.json이 생성되고, 이후 실행부터는 브라우저 없이 자동으로 인증된다.

실행 전 준비:
    - credentials.json이 프로젝트 루트에 있어야 함 (Google Cloud Console에서
      발급한 OAuth 클라이언트, 데스크톱 앱 타입)

실행:
    python scripts/verify_google_docs_auth.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.google_docs_writer import GoogleDocsWriteError, create_and_write_doc  # noqa: E402

TEST_TITLE = "[검증용] class-prep-agent Google Docs 연동 테스트"
TEST_BODY = (
    "이 문서는 google_docs_writer.py의 OAuth 인증 + 문서 생성/쓰기가 실제로 "
    "동작하는지 확인하기 위해 자동으로 만들어졌습니다.\n\n"
    "이 문서를 열어서 이 텍스트가 보이면 연동 성공입니다."
)


def main() -> None:
    print("Google 인증을 시작합니다. 브라우저가 열리지 않으면 터미널에 출력되는 URL을 직접 열어주세요...")
    try:
        result = create_and_write_doc(TEST_TITLE, TEST_BODY)
    except GoogleDocsWriteError as exc:
        print(f"실패: {exc}")
        raise SystemExit(1) from exc

    print("성공!")
    print("doc_id:", result["doc_id"])
    print("url:", result["url"])
    print("\n위 url을 열어서 본문이 잘 들어갔는지 눈으로 확인해주세요.")


if __name__ == "__main__":
    main()
