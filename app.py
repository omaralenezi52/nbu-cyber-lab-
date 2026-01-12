import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
# إضافة مكتبات التشفير الضرورية
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_me'

# إعدادات رفع الصور
UPLOAD_FOLDER = 'static/profile_pics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== دالة احتساب النقاط ====================
def award_points(user_id, challenge_id, points):
    conn = get_db_connection()
    solved = conn.execute('SELECT * FROM solved_challenges WHERE user_id = ? AND challenge_id = ?', 
                          (user_id, challenge_id)).fetchone()
    if not solved:
        conn.execute('UPDATE users SET score = score + ? WHERE id = ?', (points, user_id))
        conn.execute('INSERT INTO solved_challenges (user_id, challenge_id) VALUES (?, ?)', (user_id, challenge_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# ==================== تسجيل الدخول (تم التعديل لدعم التشفير) ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        # جلب المستخدم بناءً على الاسم فقط
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        # التحقق من صحة المستخدم ومطابقة التشفير
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            
            if user['is_admin'] == 1:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('profile'))
        else:
            msg = "خطأ في اسم المستخدم أو كلمة المرور!"
            
    return render_template('login.html', msg=msg)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== التسجيل (تم التعديل لدعم التشفير) ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        fullname = request.form['fullname']
        email = request.form['email']
        phone = request.form['phone']
        age = request.form['age']
        
        # تشفير كلمة المرور قبل الحفظ
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO users (username, password, fullname, email, phone, age, score, is_admin) 
                VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            ''', (username, hashed_password, fullname, email, phone, age))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error: {e}")
            return "حدث خطأ! قد يكون اسم المستخدم مسجلاً مسبقاً."
    return render_template('register.html')

# ==================== لوحة تحكم الأدمن ====================

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    # حماية: للأدمن فقط
    if 'user_id' not in session or session.get('is_admin') != 1:
        return "⛔ غير مصرح لك بالدخول!", 403

    conn = get_db_connection()
    
    if request.method == 'POST':
        target_id = request.form.get('user_id')
        new_score = request.form.get('score')
        if target_id and new_score:
            conn.execute('UPDATE users SET score = ? WHERE id = ?', (new_score, target_id))
            conn.commit()

    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('admin.html', users=users)

@app.route('/delete_user/<int:id>', methods=['POST'])
def delete_user(id):
    if 'user_id' not in session or session.get('is_admin') != 1:
        return "⛔ غير مصرح لك!", 403
    
    if id == session['user_id']:
        return "لا يمكنك حذف حسابك وأنت مسجل دخول!"

    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.execute('DELETE FROM solved_challenges WHERE user_id = ?', (id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_dashboard'))

# ==================== الصفحات الرئيسية ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        phone = request.form.get('phone')
        age = request.form.get('age')
        
        conn.execute('''
            UPDATE users SET fullname = ?, email = ?, phone = ?, age = ? 
            WHERE id = ?
        ''', (fullname, email, phone, age, session['user_id']))
        
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (filename, session['user_id']))
        
        conn.commit()

    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    solved = conn.execute('SELECT challenge_id FROM solved_challenges WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    
    user_data = dict(user)
    if not user_data['profile_pic']: 
        user_data['profile_pic'] = 'default.png'
        
    return render_template('profile.html', user=user_data, solved_list=solved)

@app.route('/leaderboard')
def leaderboard():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY score DESC').fetchall()
    conn.close()
    return render_template('leaderboard.html', users=users)

# ==================== التحديات ====================

@app.route('/challenges')
def challenges_list():
    challenges = [
        {'name': 'SQL Injection', 'points': 10, 'url': 'sql_challenge', 'status': 'سهل', 'desc': 'تجاوز صفحة الدخول.'},
        {'name': 'Ransomware', 'points': 20, 'url': 'ransomware_challenge', 'status': 'متوسط', 'desc': 'فك تشفير الملفات.'},
        {'name': 'Social Engineering', 'points': 15, 'url': 'social_challenge', 'status': 'سهل', 'desc': 'اكتشاف الاحتيال.'}
    ]
    return render_template('challenges.html', challenges=challenges)

@app.route('/sql_challenge', methods=['GET', 'POST'])
def sql_challenge():
    msg = ""
    if request.method == 'POST':
        user_input = request.form.get('username')
        if user_input == "' OR 1=1 --":
            if 'user_id' in session:
                if award_points(session['user_id'], 'SQL Injection', 10):
                    msg = "✅ إجابة صحيحة. تم تجاوز تسجيل الدخول!"
                else: msg = "⚠️ لقد قمت بحل هذا التحدي مسبقاً."
        else: 
            msg = "❌ خطأ. حاول استخدام ثغرة حقن SQL."     
    return render_template('sql_challenge.html', msg=msg)

@app.route('/ransomware_challenge', methods=['GET', 'POST'])
def ransomware_challenge():
    msg = ""
    if request.method == 'POST':
        if request.form.get('key') == "NoMoreRansom2025":
            if 'user_id' in session:
                if award_points(session['user_id'], 'Ransomware', 20):
                    msg = "✅ أحسنت! تم فك تشفير الملفات."
                else: msg = "⚠️ لقد قمت بحل هذا التحدي مسبقاً."
        else: msg = "❌ المفتاح غير صحيح."
    return render_template('ransomware.html', msg=msg)

@app.route('/social_challenge', methods=['GET', 'POST'])
def social_challenge():
    msg = ""
    if request.method == 'POST':
        if request.form.get('answer') == 'phishing':
            if 'user_id' in session:
                if award_points(session['user_id'], 'Social Engineering', 15):
                    msg = "✅ إجابة صحيحة! هذا كان هجوم تصيد."
                else: msg = "⚠️ لقد قمت بحل هذا التحدي مسبقاً."
        else: msg = "❌ إجابة خاطئة."
    return render_template('social_engineering.html', msg=msg)

if __name__ == '__main__':
    app.run(debug=True)