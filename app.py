
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import sqlite3
import secrets
import random


app = Flask(__name__)
secret_key = secrets.token_urlsafe(32)
app.secret_key = secret_key

def get_db_connection():
    conn = sqlite3.connect('questions.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/add", methods=['POST'])
def add_question():
    data = request.json
    question = data['question'].strip()
    q_type = data['type']
    options = data['options']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 檢查是否已有相同題目存在
    cursor.execute('SELECT id FROM questions WHERE content = ?', (question,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return jsonify({"status": "duplicate", "message": "此題目已存在"})

    # 插入題目
    cursor.execute('INSERT INTO questions (content, type) VALUES (?, ?)', (question, q_type))
    question_id = cursor.lastrowid

    # 插入選項
    for opt in options:
        cursor.execute('INSERT INTO options (question_id, content, is_correct) VALUES (?, ?, ?)',
                       (question_id, opt['content'], opt['is_correct']))

    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/form')
def add_formPage():
    return render_template('sql_form.html', title="Add Questions")

@app.route('/')
def show_list():
    conn = get_db_connection()
    questions = conn.execute('SELECT * FROM questions ORDER BY RANDOM() LIMIT 50').fetchall()
    options_raw  = conn.execute('SELECT * FROM options WHERE question_id IN ({})'.format(','.join('?' * len(questions))), [q['id'] for q in questions]).fetchall()
    conn.close()
    # 隨機打亂選項
    grouped_options = {}
    option_order = {}  # 存入 session 的用這個

    for opt in options_raw:
        qid = opt['question_id']
        grouped_options.setdefault(qid, []).append(opt)

    for qid, opt_list in grouped_options.items():
        random.shuffle(opt_list)
        grouped_options[qid] = opt_list
        option_order[qid] = [opt['id'] for opt in opt_list]  # 記住順序（用 id）
    # 將選出的 50 題保存到 session
    session['option_order'] = option_order  # 存進 session
    session['questions'] = [{'id': q['id'], 'content': q['content'], 'type': q['type']} for q in questions]
    
    return render_template('list.html', questions=questions, options=grouped_options, user_answers_map={}, score=0)

@app.route('/view')
def view_sql():
    page = request.args.get('page', 1, type=int)  # 預設頁碼為 1
    per_page = 10  # 每頁顯示 10 筆
    conn = get_db_connection()
    # 查詢總筆數
    total_questions = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    
    # 計算總頁數
    total_pages = (total_questions + per_page - 1) // per_page
    
    # 查詢當前頁的資料
    questions = conn.execute('SELECT * FROM questions ORDER BY id LIMIT ? OFFSET ?',
                             (per_page, (page - 1) * per_page)).fetchall()

    # 查詢對應的選項
    options_raw  = conn.execute('SELECT * FROM options WHERE question_id IN ({})'.format(','.join('?' * len(questions))), [q['id'] for q in questions]).fetchall()

    #questions = conn.execute('SELECT * FROM questions').fetchall()
    #options_raw = conn.execute('SELECT * FROM options').fetchall()
    correct_ids = [row['id'] for row in options_raw if row['is_correct'] == 1]
    
    grouped_options = {}
    for opt in options_raw:
        qid = opt['question_id']
        grouped_options.setdefault(qid, []).append(opt)
    conn.close()
    return render_template('sql_view.html', questions=questions, options=grouped_options, total_pages=total_pages, current_page=page, correct=correct_ids)

@app.route('/success')
def success():
    name = request.args.get("name")
    action = request.args.get("action")
    return f"{action.upper()} success! Received question: {name}"

@app.route('/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 先刪除相關選項
    cursor.execute('DELETE FROM options WHERE question_id = ?', (question_id,))
    # 再刪除題目本身
    cursor.execute('DELETE FROM questions WHERE id = ?', (question_id,))

    conn.commit()
    conn.close()
    return redirect(url_for('view_sql'))

@app.route('/check_answers', methods=['POST'])
def check_answers():
    conn = get_db_connection()
    # 從 session 讀取已選的 50 題
    questions = session.get('questions', [])
    if not questions:
        return redirect(url_for('show_list'))  # 如果 session 沒有題目，重導向到首頁
    
    # 抓選項
    options_raw  = conn.execute('SELECT * FROM options WHERE question_id IN ({})'.format(','.join('?' * len(questions))), [q['id'] for q in questions]).fetchall()

    # 用 session 裡的順序重建 grouped_options
    option_order = session.get('option_order', {})
    grouped_options = {}

    options_map = {opt['id']: opt for opt in options_raw}
    for qid, ordered_ids in option_order.items():
        grouped_options[int(qid)] = [options_map[int(opt_id)] for opt_id in ordered_ids]

    # 抓正確選項
    correct_options = conn.execute('SELECT * FROM options WHERE is_correct = 1').fetchall()
    conn.close()

    # 建立正確答案 map
    correct_map = {}
    for opt in correct_options:
        qid = str(opt['question_id'])
        correct_map.setdefault(qid, []).append(str(opt['id']))

    score = 0
    user_answers_map = {}
    for q in questions:
        qid = q['id']
        qtype = q['type']
        field_name = f"question_{qid}" + ("[]" if qtype == 'multipleChoice' else "")
        user_answers = request.form.getlist(field_name)
        correct_ids = correct_map.get(str(qid), [])
        user_answers_map[qid] = {  # key 是整數
            'user_answers': user_answers,
            'correct_answers': correct_ids,
            'is_correct': set(user_answers) == set(correct_ids)
        }
        if set(user_answers) == set(correct_ids):
            score += 2
    return render_template('list.html', questions=questions, options=grouped_options, user_answers_map=user_answers_map, score=score)


if __name__ == '__main__':
    app.run(debug=True)