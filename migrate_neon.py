import os
from sqlalchemy import create_all, text
from app import app, db

def migrate_neon():
    print("--- 데이터베이스 마이그레이션 시작 ---")
    
    with app.app_context():
        # 1. Post 테이블에 is_highlighted 컬럼 추가 (PostgreSQL/SQLite 공용)
        try:
            # PostgreSQL은 ALTER TABLE에서 IF NOT EXISTS를 지원하지 않는 경우가 있어 try-except로 처리
            db.session.execute(text("ALTER TABLE post ADD COLUMN is_highlighted BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("[성공] Post 테이블에 'is_highlighted' 컬럼을 추가했습니다.")
        except Exception as e:
            db.session.rollback()
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("[정보] 'is_highlighted' 컬럼이 이미 존재합니다.")
            else:
                print(f"[오류] 컬럼 추가 중 알 수 없는 에러 발생: {e}")

        # 2. 새로운 테이블 (Poll, PollOption, PollVote) 생성
        try:
            db.create_all()
            print("[성공] 모든 신규 테이블(Poll 등)이 생성/확인되었습니다.")
        except Exception as e:
            print(f"[오류] 테이블 생성 중 에러 발생: {e}")

    print("--- 마이그레이션 완료 ---")

if __name__ == "__main__":
    migrate_neon()
