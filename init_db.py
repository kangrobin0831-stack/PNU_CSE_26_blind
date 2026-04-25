"""
init_db.py - PNU BLIND DB 강제 초기화 스크립트
----------------------------------------------
실행 방법: python init_db.py
효과: 기존 DB를 완전히 삭제하고
      최신 모델(is_admin 포함)에 맞춰 테이블을 새로 생성합니다.
----------------------------------------------
"""
import os
import sys

# app 임포트 전에 DB 파일을 먼저 삭제
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')

print("=" * 50)
print("  PNU BLIND - DB 초기화 스크립트")
print("=" * 50)

if os.path.exists(DB_PATH):
    try:
        os.remove(DB_PATH)
        print(f"[삭제 완료] {DB_PATH}")
    except PermissionError:
        print("[오류] DB 파일이 다른 프로그램(서버)에 의해 사용 중입니다.")
        print("       python app.py 서버를 먼저 종료한 후 다시 실행하세요.")
        sys.exit(1)
else:
    print("[알림] 기존 DB 파일 없음. 새로 생성합니다.")

# DB 삭제 완료 후 app 임포트 (이 시점에 db.create_all() 실행됨)
from app import app, db

with app.app_context():
    db.create_all()
    print("[완료] 최신 스키마로 테이블 생성 성공!")
    print()
    print("  생성된 테이블 목록:")
    print("  - user        (id, username, password_hash, student_id,")
    print("                 email, nickname, is_admin, login_attempts,")
    print("                 lock_until, created_at)")
    print("  - post        (id, user_id, category, title, content,")
    print("                 is_notice, recommend_count, report_count, created_at)")
    print("  - comment     (id, post_id, user_id, parent_id, content,")
    print("                 report_count, created_at)")
    print("  - recommendation (id, user_id, post_id)")
    print("  - report         (id, user_id, post_id, comment_id)")
    print()
    print("다음 단계: python app.py 를 실행하세요.")
    print("회원가입 시 학번 202655397 입력 -> 관리자 자동 지정!")
    print("=" * 50)
