import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'pnu_blind26_secret_key')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
db_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 보안: 파일 업로드 5MB 제한

# 인증 이미지 경로 (회원가입용)
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 게시글 첨부 이미지 경로 (게시판용) — 인증 이미지와 완전 분리
POST_IMAGE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'post_images')
POST_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(POST_IMAGE_FOLDER, exist_ok=True)

# 메일 서버 설정 (Gmail 기준)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

# 💡 핵심: 아이디와 비밀번호를 코드에 직접 적지 않고, Render의 환경변수에서 가져오게 합니다.
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
mail = Mail(app)
from flask_mail import Message
serializer = URLSafeTimedSerializer(app.secret_key)

# =============================================
# 헬퍼 함수
# =============================================

def get_kst_now():
    """한국 시간(KST) 반환"""
    return datetime.now(timezone(timedelta(hours=9)))

def allowed_file(filename):
    """확장자 화이트리스트 검사 (웹쉘 업로드 차단)"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =============================================
# 데이터베이스 모델
# =============================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    student_id = db.Column(db.String(9), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    nickname = db.Column(db.String(30), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)      # 관리자 승인 여부
    verification_image = db.Column(db.String(256), nullable=True)           # 인증 이미지 파일명
    login_attempts = db.Column(db.Integer, default=0, nullable=False)
    lock_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=get_kst_now)
    posts = db.relationship('Post', backref='author', cascade='all, delete-orphan', lazy=True)
    comments = db.relationship('Comment', backref='author', cascade='all, delete-orphan', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_notice = db.Column(db.Boolean, default=False, nullable=False)
    recommend_count = db.Column(db.Integer, default=0, nullable=False)
    report_count = db.Column(db.Integer, default=0, nullable=False)
    image_path = db.Column(db.String(256), nullable=True)  # 게시글 첨부 이미지
    created_at = db.Column(db.DateTime, default=get_kst_now)
    comments = db.relationship('Comment', backref='post', cascade='all, delete-orphan',
                               order_by='Comment.created_at', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    report_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=get_kst_now)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]),
                               cascade='all, delete-orphan', order_by='Comment.created_at', lazy=True)

class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)

if __name__ == '__main__':
    # Render가 지정해주는 포트를 사용하고, 모든 외부 접속(0.0.0.0)을 허용합니다.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

with app.app_context():
    db.create_all()
    print("[OK] DB 테이블 확인/생성 완료")

# =============================================
# 헬퍼 함수
# =============================================

def get_current_user():
    if 'user_id' not in session:
        return None
    return db.session.get(User, session['user_id'])

def is_admin():
    user = get_current_user()
    return bool(user and user.is_admin)

# =============================================
# 에러 핸들러
# =============================================

@app.errorhandler(403)
def forbidden(e):
    flash("접근 권한이 없습니다.")
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(413)
def file_too_large(e):
    flash("파일 용량이 5MB를 초과했습니다.")
    # Referer를 확인해 write 페이지에서 왔으면 write로, 아니면 verify로
    referrer = request.referrer or ''
    if 'write' in referrer:
        return redirect(url_for('write')), 302
    return redirect(url_for('verify')), 302

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"500: {e}")
    return render_template('errors/500.html'), 500

# =============================================
# 로그인 미들웨어
# =============================================

@app.before_request
def require_login():
    open_routes = {'login', 'signup', 'verify', 'find_id',
                   'forgot_password', 'reset_password', 'static'}
    # 이미 로그인된 상태에서 login/signup 접근 시 메인으로 리다이렉트 (루프 방지)
    if request.endpoint in ('login', 'signup') and 'user_id' in session:
        return redirect(url_for('index'))
    if request.endpoint not in open_routes and 'user_id' not in session:
        return redirect(url_for('login'))

# =============================================
# 인증 라우트
# =============================================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        student_id = request.form.get('student_id', '').strip()
        email      = request.form.get('email', '').strip()
        nickname   = request.form.get('nickname', '').strip()

        if not all([username, password, student_id, email, nickname]):
            flash("모든 항목을 입력해 주세요.")
            return redirect(url_for('signup'))
        if len(student_id) != 9 or not student_id.isdigit():
            flash("학번은 숫자 9자리여야 합니다.")
            return redirect(url_for('signup'))

        exists = User.query.filter(
            (User.username == username) |
            (User.student_id == student_id) |
            (User.email == email)
        ).first()
        if exists:
            flash("이미 사용 중인 아이디, 학번 또는 이메일입니다.")
            return redirect(url_for('signup'))

        ADMIN_STUDENT_ID = '202655397'
        admin_flag    = (student_id == ADMIN_STUDENT_ID)
        # 관리자는 자동 승인, 일반 사용자는 승인 대기
        approved_flag = admin_flag

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            student_id=student_id,
            email=email,
            nickname=nickname,
            is_admin=admin_flag,
            is_approved=approved_flag,
        )
        db.session.add(new_user)
        db.session.commit()

        # 가입 후 세션에 임시 저장 (verify 페이지에서 파일 업로드 연결용)
        session['pending_user_id'] = new_user.id

        if admin_flag:
            flash("관리자 계정으로 가입 완료! 로그인해 주세요.")
            return redirect(url_for('login'))
        else:
            flash("가입 완료! 학생 인증을 위해 캡처본을 업로드해 주세요.")
            return redirect(url_for('verify'))

    return render_template('signup.html')


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    # pending_user_id가 없으면 가입 페이지로
    user_id = session.get('pending_user_id')
    if not user_id:
        flash("먼저 회원가입을 완료해 주세요.")
        return redirect(url_for('signup'))

    user = db.session.get(User, user_id)
    if not user:
        session.pop('pending_user_id', None)
        return redirect(url_for('signup'))

    if request.method == 'POST':
        if 'verification_image' not in request.files:
            flash("파일을 선택해 주세요.")
            return redirect(url_for('verify'))

        file = request.files['verification_image']
        if file.filename == '':
            flash("파일을 선택해 주세요.")
            return redirect(url_for('verify'))

        # 보안 1: 확장자 화이트리스트 검사 (웹쉘 차단)
        if not allowed_file(file.filename):
            flash("PNG, JPG, JPEG 형식의 파일만 업로드할 수 있습니다.")
            return redirect(url_for('verify'))

        # 보안 2: UUID 파일명으로 난독화 (경로 조작 및 파일명 공격 차단)
        ext = file.filename.rsplit('.', 1)[1].lower()
        safe_filename = uuid.uuid4().hex + '.' + ext
        save_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        file.save(save_path)

        # 기존 이미지가 있으면 삭제 후 교체
        if user.verification_image:
            old_path = os.path.join(UPLOAD_FOLDER, user.verification_image)
            if os.path.exists(old_path):
                os.remove(old_path)

        user.verification_image = safe_filename
        db.session.commit()

        session.pop('pending_user_id', None)
        flash("인증 캡처본이 제출되었습니다. 과대의 승인 후 로그인할 수 있습니다.")
        return redirect(url_for('login'))

    return render_template('verify.html', user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if not user:
            flash("아이디 또는 비밀번호가 틀렸습니다.")
            return render_template('login.html')

        if user.lock_until and datetime.now(timezone.utc).replace(tzinfo=None) < user.lock_until:
            remaining = int((user.lock_until - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 60) + 1
            flash(f"연속 오류로 계정이 잠겼습니다. {remaining}분 후 다시 시도하세요.")
            return render_template('login.html')

        if not check_password_hash(user.password_hash, password):
            user.login_attempts = (user.login_attempts or 0) + 1
            if user.login_attempts >= 7:
                user.lock_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
                flash("비밀번호를 7회 틀려 30분간 계정이 잠깁니다.")
            else:
                flash(f"비밀번호가 틀렸습니다. ({user.login_attempts}/7회)")
            db.session.commit()
            return render_template('login.html')

        # 비밀번호 일치 → 승인 여부 체크
        if not user.is_approved:
            session['pending_user_id'] = user.id
            return render_template('login.html', pending_user=user)

        user.login_attempts = 0
        user.lock_until = None
        db.session.commit()
        session.clear()
        session['user_id'] = user.id
        session['username'] = user.username
        session['nickname'] = user.nickname
        session['is_admin'] = user.is_admin
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user = get_current_user()
    if request.method == 'POST':
        if not check_password_hash(user.password_hash, request.form.get('current_password', '')):
            flash("현재 비밀번호가 일치하지 않습니다.")
            return redirect(url_for('profile'))
        new_nickname = request.form.get('nickname', '').strip()
        new_email    = request.form.get('email', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('new_password_confirm', '')

        if new_password:
            if new_password != confirm_password:
                flash("새 비밀번호가 서로 일치하지 않습니다.")
                return redirect(url_for('profile'))
            user.password_hash = generate_password_hash(new_password)
            
        if new_nickname: user.nickname = new_nickname
        if new_email:    user.email    = new_email
        db.session.commit()
        session['nickname'] = user.nickname
        flash("정보가 수정되었습니다.")
        return redirect(url_for('profile'))

    my_posts    = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    my_comments = Comment.query.filter_by(user_id=user.id).order_by(Comment.created_at.desc()).all()
    return render_template('profile.html', user=user, my_posts=my_posts, my_comments=my_comments)


@app.route('/delete_account', methods=['POST'])
def delete_account():
    user = get_current_user()
    if check_password_hash(user.password_hash, request.form.get('password', '')):
        db.session.delete(user)
        db.session.commit()
        session.clear()
        flash("회원 탈퇴가 완료되었습니다.")
        return redirect(url_for('login'))
    flash("비밀번호가 틀렸습니다.")
    return redirect(url_for('profile'))


@app.route('/find_id', methods=['GET', 'POST'])
def find_id():
    if request.method == 'POST':
        user = User.query.filter_by(
            student_id=request.form.get('student_id', '').strip(),
            email=request.form.get('email', '').strip()
        ).first()
        flash(f"아이디: [{user.username}]" if user else "일치하는 정보가 없습니다.")
    return render_template('find_id.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        user = User.query.filter_by(
            username=request.form.get('username', '').strip(),
            email=request.form.get('email', '').strip()
        ).first()
        if user:
            token     = serializer.dumps(user.email, salt='pw-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # 메일 발송 로직
            try:
                msg = Message("[PNU CSE 26' BLIND] 비밀번호 재설정 링크",
                              recipients=[user.email])
                msg.body = f"""안녕하세요, {user.nickname}님.
비밀번호를 재설정하려면 아래 링크를 클릭하세요 (10분 내 유효):
{reset_url}

본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.
"""
                mail.send(msg)
                flash("입력하신 이메일로 비밀번호 재설정 링크를 발송했습니다.")
            except Exception as e:
                app.logger.error(f"Mail send error: {e}")
                flash("메일 발송 중 오류가 발생했습니다. 관리자에게 문의하세요.")
        else:
            flash("일치하는 정보가 없습니다.")
    return render_template('forgot_password.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='pw-reset', max_age=600)
    except Exception:
        flash("링크가 만료되었거나 유효하지 않습니다.")
        return redirect(url_for('login'))
    if request.method == 'POST':
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(request.form.get('password', ''))
            db.session.commit()
            flash("비밀번호가 재설정되었습니다.")
            return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

# =============================================
# 게시판 라우트
# =============================================

@app.route('/')
def index():
    category     = request.args.get('category')
    search_query = request.args.get('q', '').strip()
    search_type  = request.args.get('search_type', 'title_content')
    sort_option  = request.args.get('sort', 'latest')
    page         = request.args.get('page', 1, type=int)

    hot_posts    = Post.query.filter(Post.recommend_count >= 10)\
                             .order_by(Post.created_at.desc()).limit(3).all()
    q = Post.query
    if category:
        q = q.filter_by(category=category)
    
    if search_query:
        if search_type == 'title':
            q = q.filter(Post.title.contains(search_query))
        elif search_type == 'content':
            q = q.filter(Post.content.contains(search_query))
        else: # title_content
            q = q.filter((Post.title.contains(search_query)) |
                         (Post.content.contains(search_query)))

    if sort_option == 'likes':
        q = q.order_by(Post.is_notice.desc(), Post.recommend_count.desc(), Post.created_at.desc())
    elif sort_option == 'comments':
        q = q.outerjoin(Comment).group_by(Post.id).order_by(Post.is_notice.desc(), func.count(Comment.id).desc(), Post.created_at.desc())
    else: # latest
        q = q.order_by(Post.is_notice.desc(), Post.created_at.desc())

    per_page = 10
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    posts = pagination.items

    return render_template('index.html', posts=posts, hot_posts=hot_posts,
                           current_category=category, search_query=search_query,
                           search_type=search_type, sort_option=sort_option,
                           pagination=pagination)


@app.route('/write', methods=['GET', 'POST'])
def write():
    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '공지사항' and not is_admin():
            flash("공지사항은 관리자만 작성할 수 있습니다.")
            return redirect(url_for('write'))

        # 게시글 이미지 보안 업로드
        saved_image = None
        file = request.files.get('post_image')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
            if ext not in POST_ALLOWED_EXTENSIONS:
                flash("이미지는 PNG, JPG, JPEG, GIF 형식만 가능합니다.")
                return redirect(url_for('write'))
            # 보안: UUID로 파일명 난독화 (경로 조작 공격 차단)
            safe_name = uuid.uuid4().hex + '.' + ext
            file.save(os.path.join(POST_IMAGE_FOLDER, safe_name))
            saved_image = safe_name

        db.session.add(Post(
            user_id=session['user_id'],
            category=category,
            title=request.form.get('title', '').strip(),
            content=request.form.get('content', '').strip(),
            is_notice=(category == '공지사항'),
            image_path=saved_image,
        ))
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('write.html', is_admin=is_admin())


@app.route('/post/<int:post_id>')
def view(post_id):
    post = db.get_or_404(Post, post_id)
    all_comments = []
    for c in post.comments:
        all_comments.append(c)
        all_comments.extend(c.replies)
    all_comments.sort(key=lambda x: x.created_at)
    user_to_anon = {post.user_id: '익명 (글쓴이)'}
    anon_count   = 1
    comment_map  = {}
    for c in all_comments:
        if c.user_id not in user_to_anon:
            user_to_anon[c.user_id] = f'익명 {anon_count}'
            anon_count += 1
        comment_map[c.id] = user_to_anon[c.user_id]
    # 현재 사용자의 추천 여부 확인 (toggle 버튼 UI용)
    uid = session.get('user_id')
    user_recommended = bool(
        uid and Recommendation.query.filter_by(user_id=uid, post_id=post_id).first()
    )
    return render_template('view.html', post=post, comment_map=comment_map,
                           user_recommended=user_recommended)


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if not is_admin():
        flash("수정 권한이 없습니다.")
        return redirect(url_for('view', post_id=post.id))

    if request.method == 'POST':
        category = request.form.get('category', '')
        if category == '공지사항' and not is_admin():
            flash("공지사항은 관리자만 작성할 수 있습니다.")
            return redirect(url_for('edit_post', post_id=post.id))

        file = request.files.get('post_image')
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
            if ext not in POST_ALLOWED_EXTENSIONS:
                flash("이미지는 PNG, JPG, JPEG, GIF 형식만 가능합니다.")
                return redirect(url_for('edit_post', post_id=post.id))
            
            # 기존 이미지가 있으면 삭제
            if post.image_path:
                try:
                    img_path = os.path.join(POST_IMAGE_FOLDER, post.image_path)
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except Exception as e:
                    app.logger.warning(f"[edit_post] old image remove failed: {e}")

            safe_name = uuid.uuid4().hex + '.' + ext
            file.save(os.path.join(POST_IMAGE_FOLDER, safe_name))
            post.image_path = safe_name

        post.category = category
        post.title = request.form.get('title', '').strip()
        post.content = request.form.get('content', '').strip()
        post.is_notice = (category == '공지사항')
        db.session.commit()
        return redirect(url_for('view', post_id=post.id))

    return render_template('edit.html', post=post, is_admin=is_admin())


@app.route('/post/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id == session.get('user_id') or is_admin():
        # 이미지 파기: 파일 오류가 나도 DB 삭제는 반드시 실행
        if post.image_path:
            try:
                img_path = os.path.join(POST_IMAGE_FOLDER, post.image_path)
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as e:
                app.logger.warning(f"[delete_post] image remove failed (ignored): {e}")
        # 이미지 파기 성공/실패와 무관하게 반드시 DB에서 삭제
        try:
            db.session.delete(post)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"[delete_post] DB delete failed: {e}")
    return redirect(url_for('index'))


@app.route('/post/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    if not session.get('user_id'):
        flash("로그인이 필요한 서비스입니다.")
        return redirect(url_for('login'))
    content   = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id') or None
    if content:
        db.session.add(Comment(
            post_id=post_id, user_id=session['user_id'],
            parent_id=parent_id, content=content,
        ))
        db.session.commit()
    return redirect(url_for('view', post_id=post_id))


@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    pid     = comment.post_id
    if comment.user_id == session.get('user_id') or is_admin():
        db.session.delete(comment)
        db.session.commit()
    return redirect(url_for('view', post_id=pid))

# =============================================
# 추천 / 신고
# =============================================

@app.route('/post/<int:post_id>/recommend', methods=['POST'])
def recommend_post(post_id):
    post = db.get_or_404(Post, post_id)
    uid  = session.get('user_id')
    if not uid:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    existing = Recommendation.query.filter_by(user_id=uid, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        post.recommend_count = max(0, post.recommend_count - 1)
        recommended = False
    else:
        db.session.add(Recommendation(user_id=uid, post_id=post_id))
        post.recommend_count += 1
        recommended = True
    db.session.commit()
    return jsonify({
        'success': True,
        'recommended': recommended,
        'recommend_count': post.recommend_count
    })


@app.route('/post/<int:post_id>/report', methods=['POST'])
def report_post(post_id):
    post = db.get_or_404(Post, post_id)
    uid  = session['user_id']
    if not Report.query.filter_by(user_id=uid, post_id=post_id).first():
        db.session.add(Report(user_id=uid, post_id=post_id))
        post.report_count += 1
        db.session.commit()
        flash("신고가 접수되었습니다.")
    else:
        flash("이미 신고한 게시글입니다.")
    return redirect(url_for('view', post_id=post_id))


@app.route('/comment/<int:comment_id>/report', methods=['POST'])
def report_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    uid     = session['user_id']
    if not Report.query.filter_by(user_id=uid, comment_id=comment_id).first():
        db.session.add(Report(user_id=uid, comment_id=comment_id))
        comment.report_count += 1
        db.session.commit()
        flash("댓글 신고가 접수되었습니다.")
    else:
        flash("이미 신고한 댓글입니다.")
    return redirect(url_for('view', post_id=comment.post_id))

# =============================================
# 관리자 대시보드
# =============================================

@app.route('/admin_pnu_hidden_26')
def admin_dashboard():
    if not is_admin(): abort(403)
    all_users         = User.query.all()
    user_count        = len(all_users)
    today_posts       = Post.query.filter(Post.created_at >= datetime.now(timezone.utc).date()).count()
    pending_users     = User.query.filter_by(is_approved=False, is_admin=False).all()
    reported_posts    = Post.query.filter(Post.report_count > 0).all()
    reported_comments = Comment.query.filter(Comment.report_count > 0).all()
    return render_template('admin_dashboard.html',
                           all_users=all_users,
                           user_count=user_count,
                           today_posts=today_posts,
                           pending_users=pending_users,
                           reported_posts=reported_posts,
                           reported_comments=reported_comments)


@app.route('/admin/user/<int:user_id>/approve', methods=['POST'])
def admin_approve_user(user_id):
    if not is_admin(): abort(403)
    user = db.get_or_404(User, user_id)
    user.is_approved = True
    db.session.commit()
    flash(f"{user.nickname}님의 가입을 승인했습니다.")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<int:user_id>/reject', methods=['POST'])
def admin_reject_user(user_id):
    """반려: DB 삭제 + 업로드 이미지 파일 영구 파기 (보안 3)"""
    if not is_admin(): abort(403)
    user = db.get_or_404(User, user_id)

    # 보안: 서버에서 인증 이미지 파일 완전 삭제
    if user.verification_image:
        img_path = os.path.join(UPLOAD_FOLDER, user.verification_image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(user)
    db.session.commit()
    flash("해당 사용자를 반려하고 인증 이미지를 서버에서 삭제했습니다.")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<int:user_id>/kick', methods=['POST'])
def admin_kick_user(user_id):
    """강퇴: DB 삭제 (Cascade로 작성글/댓글 자동삭제 됨) + 업로드 이미지 파일 파기"""
    if not is_admin(): abort(403)
    if user_id == session.get('user_id'):
        flash("자기 자신은 강퇴할 수 없습니다.")
        return redirect(url_for('admin_dashboard'))

    user = db.get_or_404(User, user_id)
    uid = user.id

    try:
        # 1. 사용자가 쓴 글의 관련 정보(이미지, 추천, 신고) 선삭제
        posts = Post.query.filter_by(user_id=uid).all()
        for p in posts:
            Recommendation.query.filter_by(post_id=p.id).delete()
            Report.query.filter_by(post_id=p.id).delete()
            if p.image_path:
                p_img_path = os.path.join(POST_IMAGE_FOLDER, p.image_path)
                if os.path.exists(p_img_path):
                    try: os.remove(p_img_path)
                    except: pass

        # 2. 사용자가 쓴 댓글의 신고 기록 삭제
        comments = Comment.query.filter_by(user_id=uid).all()
        for c in comments:
            Report.query.filter_by(comment_id=c.id).delete()

        # 3. 사용자가 직접 행한 신고 및 추천 기록 삭제
        Report.query.filter_by(user_id=uid).delete()
        Recommendation.query.filter_by(user_id=uid).delete()

        # 4. 사용자 인증 이미지 삭제
        if user.verification_image:
            img_path = os.path.join(UPLOAD_FOLDER, user.verification_image)
            if os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass

        # 5. 최종 사용자 삭제
        db.session.delete(user)
        db.session.commit()
        flash(f"사용자({user.nickname})가 성공적으로 강퇴 처리되었습니다.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Kick failed for user {uid}: {e}")
        flash("강퇴 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/post/<int:post_id>/reset_report', methods=['POST'])
def admin_reset_post_report(post_id):
    if not is_admin(): abort(403)
    post = db.get_or_404(Post, post_id)
    post.report_count = 0
    Report.query.filter_by(post_id=post_id).delete()
    db.session.commit()
    flash("게시글 신고를 초기화했습니다.")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/comment/<int:comment_id>/reset_report', methods=['POST'])
def admin_reset_comment_report(comment_id):
    if not is_admin(): abort(403)
    comment = db.get_or_404(Comment, comment_id)
    comment.report_count = 0
    Report.query.filter_by(comment_id=comment_id).delete()
    db.session.commit()
    flash("댓글 신고를 초기화했습니다.")
    return redirect(url_for('admin_dashboard'))


# =============================================
# SEO (Robots.txt & Sitemap)
# =============================================

@app.route('/robots.txt')
def robots_txt():
    content = [
        "User-agent: *",
        "Disallow: /admin/",      # 관리자 페이지 비노출
        "Disallow: /post/",       # 게시글 상세 내역 비노출 (프라이버시 보호)
        "Disallow: /profile",     # 프로필 페이지 비노출
        f"Sitemap: {url_for('sitemap_xml', _external=True)}"
    ]
    return Response("\n".join(content), mimetype="text/plain")

@app.route('/sitemap.xml')
def sitemap_xml():
    # 메인 페이지 및 카테고리별 URL 생성
    categories = ['', '공지사항', '자유게시판', '학습/질문', '동아리/MT', '건의사항']
    pages = []
    
    # 도메인 정보 (배포 환경에 맞춰 자동 생성)
    base_url = request.url_root.rstrip('/')
    
    for cat in categories:
        url = f"{base_url}{url_for('index', category=cat if cat else None)}"
        pages.append(f"""
    <url>
        <loc>{url}</loc>
        <changefreq>daily</changefreq>
        <priority>{'1.0' if not cat else '0.8'}</priority>
    </url>""")

    sitemap_content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(pages) + '\n</urlset>'
    return Response(sitemap_content, mimetype="application/xml")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Render가 지정해주는 포트를 사용하고, 모든 외부 접속(0.0.0.0)을 허용합니다.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
