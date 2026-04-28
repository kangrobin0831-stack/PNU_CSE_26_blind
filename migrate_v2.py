import os
import sqlite3
from app import app, db

def migrate():
    db_path = os.path.join(app.instance_path, 'database.db')
    if not os.path.exists(db_path):
        print("데이터베이스 파일이 없습니다. 초기 생성을 진행합니다.")
        with app.app_context():
            db.create_all()
        return

    print(f"데이터베이스({db_path}) 업데이트를 시작합니다...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Post 테이블에 is_highlighted 컬럼 추가 시도
    try:
        cursor.execute("ALTER TABLE post ADD COLUMN is_highlighted BOOLEAN DEFAULT 0")
        print("- Post 테이블에 'is_highlighted' 컬럼을 추가했습니다.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("- Post 테이블에 이미 'is_highlighted' 컬럼이 존재합니다.")
        else:
            print(f"- Post 업데이트 중 오류 발생: {e}")

    conn.commit()
    conn.close()

    # 2. 새로운 테이블(Poll, PollOption, PollVote) 생성
    with app.app_context():
        db.create_all()
        print("- 새로운 테이블(Poll 등) 생성을 확인했습니다.")

    print("\n마이그레이션이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    migrate()
