import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import random
import re
import requests
import base64
import io
import datetime
from gtts import gTTS
from streamlit_gsheets import GSheetsConnection

# ==============================================================================
# 初始化
# ==============================================================================
st.set_page_config(page_title="多益學習APP", page_icon="📱", layout="centered")

DB_NAME = "toeic_pro.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocabs 
                 (id INTEGER PRIMARY KEY, word TEXT UNIQUE, pos TEXT, 
                  definition TEXT, example TEXT, point TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress 
                 (user_id TEXT, vocab_id INTEGER, wrong_count INTEGER DEFAULT 0, 
                  correct_streak INTEGER DEFAULT 0, last_tested TIMESTAMP,
                  PRIMARY KEY (user_id, vocab_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 工具函式：過濾中文
# ==============================================================================
def remove_chinese(text):
    """使用正則表達式移除字串中的中文字元"""
    if not text:
        return ""
    # 移除中文範圍字元
    return re.sub(r'[\u4e00-\u9fff]+', '', text).strip()

# ==============================================================================
# 自動同步功能 (10天一次)
# ==============================================================================
def auto_sync_logic():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM system_config WHERE key = 'last_sync'")
    res = c.fetchone()
    today = datetime.date.today()
    
    need_sync = False
    if res is None:
        need_sync = True
    else:
        last_date = datetime.datetime.strptime(res[0], '%Y-%m-%d').date()
        if (today - last_date).days >= 10:
            need_sync = True
            
    if need_sync:
        try:
            sync_data()
            c.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('last_sync', ?)", (today.isoformat(),))
            conn.commit()
        except:
            pass
    conn.close()

# ==============================================================================
# SESSION SAFE INIT
# ==============================================================================
def init_session():
    if "state" not in st.session_state:
        st.session_state.state = "q"
    if "score" not in st.session_state:
        st.session_state.score = 0
    if "streak" not in st.session_state:
        st.session_state.streak = 0
    if "count" not in st.session_state:
        st.session_state.count = 1
    if "q" not in st.session_state:
        st.session_state.q = None
    if "wrong_list" not in st.session_state:
        st.session_state.wrong_list = []
    if "selected" not in st.session_state:
        st.session_state.selected = None

# ==============================================================================
# 同步與出題邏輯
# ==============================================================================
def sync_data():
    conn_gs = st.connection("gsheets", type=GSheetsConnection)
    df_gs = conn_gs.read()
    conn_db = sqlite3.connect(DB_NAME)
    for _, row in df_gs.iterrows():
        conn_db.execute('''INSERT OR REPLACE INTO vocabs 
        (word, pos, definition, example, point)
        VALUES (?, ?, ?, ?, ?)''', 
        (row['word'], row['pos'], row['definition'], row['example'], row['point']))
    conn_db.commit()
    conn_db.close()

def get_weighted_question(user_id, practice_mode):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
    SELECT v.*, IFNULL(p.wrong_count,0) as wrongs, IFNULL(p.correct_streak,0) as streak
    FROM vocabs v LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?
    """, conn, params=(user_id,))
    if df.empty: return None
    if practice_mode == "錯題":
        df = df[df['wrongs'] > 0]
        if df.empty: return None
    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)
    target = df.sample(n=1, weights='weight').iloc[0]
    dist = pd.read_sql_query("SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3", conn, params=(target['word'],))
    options = dist['word'].tolist() + [target['word']]
    random.shuffle(options)
    conn.close()
    return {
        "id": int(target['id']), "word": target['word'], "definition": target['definition'],
        "example": target['example'], "point": target['point'], "pos": target['pos'],
        "options": options, "correct": target['word']
    }

def get_cloze_question(user_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT v.*, IFNULL(p.wrong_count,0) as wrongs, IFNULL(p.correct_streak,0) as streak
        FROM vocabs v LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?
        WHERE v.example IS NOT NULL AND v.example != ''
    """, conn, params=(user_id,))
    
    if df.empty: 
        conn.close()
        return None

    # 權重隨機抽題
    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)
    target = df.sample(n=1, weights='weight').iloc[0]
    
    full_sentence = str(target['example'])
    word = str(target['word'])
    
    # 🔥 核心修正：先在含有中文的句子中挖空，確保一定能挖成功
    blanked = re.sub(re.escape(word), " ______ ", full_sentence, flags=re.IGNORECASE)
    # 挖空後，再移除句子中的中文，確保題目是全英文
    blank_sentence = remove_chinese(blanked)
    
    dist = pd.read_sql_query("SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3", conn, params=(word,))
    options = dist['word'].tolist() + [word]
    random.shuffle(options)
    conn.close()
    
    return {
        "id": int(target["id"]), "sentence": blank_sentence, "answer": word,
        "options": options, "example": full_sentence, "point": target["point"], "word": word
    }

def create_audio_button(text, button_text, theme_mode):
    if not text: return
    clean_text = remove_chinese(text)
    clean_text = re.sub(r'[^a-zA-Z0-9\s\.,?!]', '', clean_text)
    try:
        tts = gTTS(text=clean_text, lang='en')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        audio_base64 = base64.b64encode(mp3_fp.getvalue()).decode()
        bg_color = "#262730" if theme_mode == "深色" else "#F0F2F6"
        text_color = "white" if theme_mode == "深色" else "#31333F"
        html_code = f"""<audio id="ap" src="data:audio/mp3;base64,{audio_base64}"></audio>
        <button onclick="document.getElementById('ap').play()" style="width:100%;padding:10px;border-radius:10px;background:{bg_color};color:{text_color};border:none;">{button_text}</button>"""
        components.html(html_code, height=50)
    except: pass

# ==============================================================================
# UI 與 主流程
# ==============================================================================
st.sidebar.title("設定")
user_id = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("模式", ["測驗", "新增單字庫"])
practice_mode = st.sidebar.selectbox("練習模式", ["單字", "填空", "錯題"])
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

init_session()
auto_sync_logic()

card_bg = "#111827" if theme_mode == "深色" else "#ffffff"
text_c = "white" if theme_mode == "深色" else "#1f2937"
st.markdown(f"""<style>.card {{background:{card_bg}; padding:30px; border-radius:20px; text-align:center; margin-bottom:20px; box-shadow:0 4px 6px rgba(0,0,0,0.1);}} .big {{font-size:24px; color:{text_c}; font-weight:600; line-height:1.5;}} .banner-img {{width:100%; height:150px; object-fit:cover; border-radius:15px; margin-bottom:15px;}}</style>""", unsafe_allow_html=True)

if mode == "測驗":
    if not user_id: st.warning("請輸入User ID"); st.stop()
    TOTAL = 10
    if st.session_state.q is None:
        if practice_mode == "填空": 
            st.session_state.q = get_cloze_question(user_id)
        else: 
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q
    if q is None: st.warning("目前沒有題目"); st.stop()

    st.progress(min(st.session_state.count / TOTAL, 1.0))
    st.markdown(f"🏆 {st.session_state.score}　🔥 {st.session_state.streak}")
    st.markdown('<img src="https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=800&q=80" class="banner-img">', unsafe_allow_html=True)

    if practice_mode == "填空":
        display_text = q.get("sentence", "") 
    else:
        display_text = q.get("definition", "")

    st.markdown(f'<div class="card"><div class="big">{display_text}</div></div>', unsafe_allow_html=True)

    if st.session_state.state == "q":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True):
                st.session_state.selected = opt
                st.session_state.state = "result"
                st.rerun()
    else:
        correct = q.get("answer") or q.get("correct")
        is_correct = st.session_state.selected == correct
        
        if is_correct:
            st.success("✅ Correct")
            st.session_state.score += 10; st.session_state.streak += 1
        else:
            st.error(f"❌ {correct}")
            st.session_state.wrong_list.append(q)
        
        st.markdown("### 📌 解析")
        st.write(f"**例句：** {q.get('example', '')}")
        st.write(f"**重點：** {q.get('point', '')}")

        col1, col2 = st.columns(2)
        with col1: create_audio_button(q.get("word",""), "🔊 單字", theme_mode)
        with col2: create_audio_button(q.get("example",""), "📢 例句", theme_mode)

        if st.button("下一題", type="primary", use_container_width=True):
            st.session_state.q = None; st.session_state.state = "q"; st.session_state.count += 1
            st.rerun()

elif mode == "新增單字庫":
    st.subheader("新增單字")
    url = st.secrets["connections"]["gsheets"].get("script_url")
    with st.form("add"):
        w = st.text_input("word")
        d = st.text_input("definition")
        ex = st.text_area("example")
        pt = st.text_area("point")
        if st.form_submit_button("送出"):
            requests.post(url, json={"method": "write", "word": w, "definition": d, "example": ex, "point": pt})
            st.success("完成")
