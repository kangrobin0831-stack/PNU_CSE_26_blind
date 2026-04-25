import os
from app import app, db

def reset_database():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
    
    # 1. 기존 DB 파일 삭제
    if os.path.exists(db_path):
        print(f"기존 데이터베이스({db_path})를 삭제합니다...")
        try:
            os.remove(db_path)
            print("삭제 완료.")
        except PermissionError:
            print("[오류] DB 파일이 사용 중입니다. 서버를 종료하고 다시 시도하세요.")
            return
    
    # 2. 새로운 테이블 생성
    with app.app_context():
        print("새로운 데이터베이스 테이블을 생성합니다...")
        db.create_all()
        print("테이블 생성 및 초기화 완료!")

if __name__ == "__main__":
    reset_database()
