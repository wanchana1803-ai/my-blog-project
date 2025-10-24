# app.py

# --- 1. Imports (นำเข้าเครื่องมือทั้งหมด) ---
import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from datetime import datetime

# --- 2. App Initialization (สร้างแอป) ---
app = Flask(__name__)

# --- 3. Configurations (ตั้งค่าแอป) ---
# (สำคัญ!) ตั้งค่า Secret Key สำหรับเซสชัน (Session)
# ให้เปลี่ยนเป็นข้อความลับของคุณเอง!
app.config['SECRET_KEY'] = 'a_very_secret_key_that_no_one_knows_123'
# ตั้งค่าตำแหน่งฐานข้อมูล
# (ใหม่!) ตรวจจับฐานข้อมูลอัตโนมัติ
# 1. พยายามดึง DATABASE_URL จาก "Environment Variable" (ที่ Render จะตั้งให้)
DATABASE_URL = os.environ.get('DATABASE_URL_RENDER')

if DATABASE_URL:
    # ถ้าเจอ (แปลว่าเราอยู่บน Render)

    # (หมายเหตุ: Render ใช้ 'postgres://' แต่ SQLAlchemy ชอบ 'postgresql://'
    #  โค้ดนี้จะช่วยแปลงให้ถูกต้องอัตโนมัติ)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # ถ้าไม่เจอ (แปลว่าเรายังอยู่บนคอมเรา)
    # ให้ใช้ฐานข้อมูล sqlite เดิมต่อไป
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 4. Extensions Initialization (สร้างอ็อบเจกต์ส่วนขยาย) ---
db = SQLAlchemy(app)        # สำหรับฐานข้อมูล
bcrypt = Bcrypt(app)        # สำหรับแฮชรหัสผ่าน
login_manager = LoginManager() # สำหรับจัดการการล็อกอิน
login_manager.init_app(app) # ผูก LoginManager กับ app
login_manager.login_view = 'login' # บอกว่าถ้าจะเข้าหน้า @login_required ให้ส่งไปที่ 'login'


# --- 5. User Loader Function (สำหรับ Flask-Login) ---
# Flask-Login ใช้ฟังก์ชันนี้เพื่อดึง User จาก ID ที่เก็บไว้ในเซสชัน
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# vvv นี่คือ "ยาม" คนใหม่ของเรา vvv
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. เช็คว่าล็อกอินหรือยัง
        if not current_user.is_authenticated:
            # ถ้ายังไม่ได้ล็อกอิน ให้ส่งไปหน้า login
            return redirect(url_for('login'))
        # 2. (สำคัญ!) เช็คว่าเป็นแอดมินหรือไม่
        if not current_user.is_admin:
            # ถ้าล็อกอินแล้ว แต่ไม่ใช่แอดมิน
            # ให้แสดงหน้า Error 403 (Forbidden/ไม่มีสิทธิ์)
            abort(403) 
        # 3. ถ้าผ่านทุกด่าน ก็อนุญาตให้ทำฟังก์ชันเดิม (f) ต่อไป
        return f(*args, **kwargs)
    return decorated_function
# ^^^ สิ้นสุดยามคนใหม่ ^^^

# ... (โค้ดของ @login_manager.user_loader) ...


# --- 6. Database Models (พิมพ์เขียวฐานข้อมูล) ---
# (โมเดล User ที่รองรับ Flask-Login และมีความสัมพันธ์กับ Post)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False) # จะเก็บเป็นแฮช

    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    # (ใหม่!) ความสัมพันธ์: ผู้ใช้ 1 คน มีได้หลายโพสต์
    # backref='author' จะสร้างคอลัมน์เสมือน .author ให้กับ Post
    posts = db.relationship('Post', backref='author', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

# (ใหม่!) โมเดล Post
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    
    # (ใหม่!) Foreign Key ที่เชื่อมไปยัง 'user.id'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Post {self.title}>'


# --- 7. Routes (เส้นทางเว็บ) ---

# --- (หน้าทั่วไป) ---
@app.route('/')
def home():
    all_posts = Post.query.order_by(Post.date_posted.desc()).all()

    return render_template('index.html', posts=all_posts)

@app.route('/about')
def about():
    return render_template('about.html')

# --- (ระบบสมาชิก: Register, Login, Logout) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # แฮชรหัสผ่านก่อนบันทึก
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        try:
            new_user = User(username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login')) # สมัครเสร็จ ให้ไปหน้า login
        except IntegrityError:
            db.session.rollback()
            message = "ชื่อผู้ใช้นี้มีคนใช้แล้ว!"
            return render_template('register.html', message=message)
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home')) # ถ้าล็อกอินแล้ว ก็ไม่ต้องล็อกอินซ้ำ

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        # ตรวจสอบว่า "เจอผู้ใช้" และ "รหัสผ่าน(แฮช)ตรงกัน"
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user) # สั่ง Flask-Login ให้จดจำผู้ใช้
            return redirect(url_for('home'))
        else:
            message = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
            return render_template('login.html', message=message)
            
    return render_template('login.html')

@app.route('/logout')
@login_required # ต้องล็อกอินก่อนถึงจะล็อกเอาต์ได้
def logout():
    logout_user() # สั่ง Flask-Login ให้ลืมผู้ใช้
    return redirect(url_for('home'))

# --- (ระบบ CRUD ผู้ใช้: Read, Update, Delete) ---
# (Create อยู่ใน /register แล้ว)

@app.route('/users')
@admin_required
def user_list():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@app.route('/update/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def update_user(user_id):
    # (ควรเพิ่ม Logic ตรวจสอบว่าเป็นแอดมิน หรือเป็นเจ้าของบัญชีเท่านั้น)
    user_to_update = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_username = request.form['username']
        try:
            user_to_update.username = new_username
            db.session.commit()
            return redirect(url_for('user_list'))
        except IntegrityError:
            db.session.rollback()
            message = "ชื่อผู้ใช้นี้มีคนใช้แล้ว!"
            return render_template('update.html', user=user_to_update, message=message)
    else:
        return render_template('update.html', user=user_to_update)

@app.route('/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    # (ควรเพิ่ม Logic ตรวจสอบว่าเป็นแอดมิน หรือเป็นเจ้าของบัญชีเท่านั้น)
    user_to_delete = User.query.get_or_404(user_id)
    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        return redirect(url_for('user_list'))
    except:
        return "เกิดข้อผิดพลาดในการลบ"

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        post_title = request.form['title']
        post_content = request.form['content']
        new_post_obj = Post(title=post_title, content=post_content, author=current_user)
        db.session.add(new_post_obj)
        db.session.commit()
        return redirect(url_for('home'))
    else:
        return render_template('create_post.html')

# ... (โค้ดของ @app.route('/post/new') ) ...


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required # ต้องล็อกอินก่อน
def delete_post(post_id):
    # 1. ค้นหาโพสต์จาก ID (ถ้าไม่เจอ แสดง 404)
    post_to_delete = Post.query.get_or_404(post_id)
    
    # 2. (สำคัญ!) ตรวจสอบสิทธิ์ความเป็นเจ้าของ (หรือเป็นแอดมิน)
    #    เช็คว่า "ถ้าคุณไม่ใช่เจ้าของ" และ "คุณก็ไม่ใช่แอดมิน"
    if post_to_delete.author != current_user and not current_user.is_admin:
        # ถ้าไม่ใช่ทั้งสองอย่าง -> เด้งกลับ
        abort(403) # (ใช้ abort(403) ดีกว่า redirect ครับ เพราะเป็นการบอกว่า "ไม่มีสิทธิ์")
        
    # 3. (ถ้าเป็นเจ้าของ) สั่งลบและบันทึก
    try:
        db.session.delete(post_to_delete)
        db.session.commit()
        return redirect(url_for('home')) # ลบเสร็จ กลับหน้าแรก
    except:
        return "เกิดข้อผิดพลาดในการลบโพสต์"

# ... (โค้ดของ @app.route('/post/<int:post_id>/delete') ) ...


# --- (ใหม่!) ระบบบล็อก: แก้ไขโพสต์ ---
@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required # ต้องล็อกอินก่อน
def update_post(post_id):
    # 1. ค้นหาโพสต์จาก ID
    post_to_update = Post.query.get_or_404(post_id)
    
    # 2. (สำคัญ!) ตรวจสอบสิทธิ์ความเป็นเจ้าของ (หรือเป็นแอดมิน)
    if post_to_update.author != current_user and not current_user.is_admin:
        abort(403) # ไม่ใช่เจ้าของ และไม่ใช่แอดมิน -> ไม่มีสิทธิ์
        
    # 3. ถ้าผู้ใช้ "ส่ง" ฟอร์ม (POST)
    if request.method == 'POST':
        # 4. ดึงข้อมูลใหม่จากฟอร์ม
        post_to_update.title = request.form['title']
        post_to_update.content = request.form['content']
        
        # 5. บันทึก (Commit) การเปลี่ยนแปลง
        try:
            db.session.commit()
            return redirect(url_for('home')) # แก้ไขเสร็จ กลับหน้าแรก
        except:
            return "เกิดข้อผิดพลาดในการแก้ไขโพสต์"
    
    # 6. ถ้าผู้ใช้ "ขอ" ดูหน้า (GET)
    else:
        # 7. แสดงหน้าฟอร์ม update.html
        #    (สำคัญ!) เราส่ง 'post=post_to_update' เข้าไปด้วย
        #    เพื่อให้ฟอร์มสามารถดึงข้อมูลเก่า (post.title, post.content) ไปแสดงได้
        return render_template('update_post.html', post=post_to_update)

# ... (โค้ด Route อื่นๆ) ...

# -----------------------------------------------
# !!! ROUGE ลับสำหรับ "สร้างตาราง" (ชั่วคราว) !!!
# (เราจะลบทิ้งทีหลัง)
# -----------------------------------------------
@app.route('/Top_22062520') # <-- เปลี่ยนเป็นรหัสลับของคุณ
def init_database():
    try:
        db.create_all() # <-- นี่คือคำสั่งที่เราต้องการรัน!
        return "SUCCESS: ตารางทั้งหมดถูกสร้างขึ้นแล้ว!"
    except Exception as e:
        return f"เกิดข้อผิดพลาด: {str(e)}", 500


# ... (โค้ด Route อื่นๆ) ...

# -----------------------------------------------
# !!! ROUGE ลับสำหรับ "เลื่อนขั้น ADMIN" (ชั่วคราว) !!!
# (เราจะลบทิ้งทีหลัง)
# -----------------------------------------------
@app.route('/Top_22062520') # <-- เปลี่ยนเป็นรหัสลับใหม่ของคุณ
@login_required # (สำคัญ!) ต้องล็อกอินก่อนถึงจะกดได้
def promote_to_admin():
    # vvv เปลี่ยน 'admin' ให้ตรงกับชื่อที่คุณเพิ่งสมัคร vvv
    if current_user.username != 'wanchana': 
        return "คุณไม่ใช่ผู้ใช้ที่กำหนดไว้", 403
        
    try:
        current_user.is_admin = True # <-- สั่งเลื่อนขั้น!
        db.session.commit()
        return "SUCCESS: คุณได้เป็น Admin แล้ว! กลับไปลบ Route นี้ใน app.py ทันที!"
    except Exception as e:
        db.session.rollback()
        return f"เกิดข้อผิดพลาด: {str(e)}", 500

# ... (โค้ด if __name__ == '__main__':) ...

# --- 8. Run the App ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)