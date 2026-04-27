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
# 需求修正：針對「英文.(中文)」格式的過濾邏輯
# ==============================================================================
def filter_only_english(text):
    """針對固定格式：英文.(中文) ，只取左括號前的內容"""
    if not text:
        return ""
    if "(" in text:
        # 取得左括號前面的所有文字
        return text.split("(")[0].strip()
    return text.strip()

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
    # 🔥 新增：紀錄上一次的練習模式，解決切換不顯示問題
    if "last_practice_mode" not in st.session_state:
        st.session_state.last_practice_mode = ""

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

    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)
    target = df.sample(n=1, weights='weight').iloc[0]
    
    full_example = str(target['example'])
    word = str(target['word'])
    
    # 🔥 關鍵修正：先只擷取英文部分，再做挖空
    english_part = filter_only_english(full_example)
    blank_sentence = re.sub(re.escape(word), " ______ ", english_part, flags=re.IGNORECASE)
    
    dist = pd.read_sql_query("SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3", conn, params=(word,))
    options = dist['word'].tolist() + [word]
    random.shuffle(options)
    conn.close()
    
    return {
        "id": int(target["id"]), "sentence": blank_sentence, "answer": word,
        "options": options, "example": full_example, "point": target["point"], "word": word
    }

def create_audio_button(text, button_text, theme_mode):
    if not text: return
    # 發音也只發英文部分
    clean_text = filter_only_english(text)
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
st.sidebar.title("🛠️ 設定")
user_id = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("模式", ["測驗", "新增單字庫"])
practice_mode = st.sidebar.selectbox("練習模式", ["單字", "填空", "錯題"])
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

init_session()
auto_sync_logic()

# 🔥 修正 Bug：偵測練習模式切換
if st.session_state.last_practice_mode != practice_mode:
    st.session_state.q = None
    st.session_state.state = "q"
    st.session_state.last_practice_mode = practice_mode

# CSS 樣式優化
card_bg = "#111827" if theme_mode == "深色" else "#ffffff"
text_c = "white" if theme_mode == "深state" else "#1f2937"
st.markdown(f"""
<style>
    .card {{
        background:{card_bg}; 
        padding:35px; 
        border-radius:24px; 
        text-align:center; 
        margin-bottom:20px; 
        box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);
        border: 1px solid {'#374151' if theme_mode == "深色" else '#e5e7eb'};
    }} 
    .big {{
        font-size:26px; 
        color:{text_c}; 
        font-weight:700; 
        line-height:1.4;
    }} 
    .banner-img {{
        width:100%; 
        height:180px; 
        object-fit:cover; 
        border-radius:20px; 
        margin-bottom:20px;
    }}
    h1 {{
        text-align: center;
        color: {text_c};
    }}
</style>
""", unsafe_allow_html=True)

if mode == "測驗":
    if not user_id: st.warning("請輸入User ID"); st.stop()
    
    # 🎨 UI 優化：標題與橫幅
    st.title("🚀 TOEIC Pro 學習助手")
    st.markdown('<img src="https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=800&q=80" class="banner-img">', unsafe_allow_html=True)
    
    TOTAL = 10
    if st.session_state.q is None:
        if practice_mode == "填空": 
            st.session_state.q = get_cloze_question(user_id)
        else: 
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q
    if q is None: st.warning("目前沒有題目"); st.stop()

    st.progress(min(st.session_state.count / TOTAL, 1.0))
    st.markdown(f"🏆 積分: **{st.session_state.score}**　🔥 連勝: **{st.session_state.streak}**")
    
    # 題目顯示邏輯
    if practice_mode == "填空":
        display_text = q.get("sentence", "") 
    else:
        display_text = q.get("definition", "")

    st.markdown(f'<div class="card"><div class="big">{display_text}</div></div>', unsafe_allow_html=True)

    if st.session_state.state == "q":
        # 優化按鈕排列（使用 columns 讓畫面不擁擠）
        cols = st.columns(2)
        for i, opt in enumerate(q["options"]):
            with cols[i % 2]:
                if st.button(opt, use_container_width=True, key=f"btn_{i}"):
                    st.session_state.selected = opt
                    st.session_state.state = "result"
                    st.rerun()
    else:
        correct = q.get("answer") or q.get("correct")
        is_correct = st.session_state.selected == correct
        
        if is_correct:
            st.success("✅ Correct! 太棒了！")
            st.session_state.score += 10; st.session_state.streak += 1
        else:
            st.error(f"❌ 錯誤。正確答案是: {correct}")
            st.session_state.wrong_list.append(q)
        
        st.markdown("### 📌 深度解析")
        st.write(f"**例句：** {q.get('example', '')}")
        st.write(f"**考點：** {q.get('point', '')}")

        col1, col2 = st.columns(2)
        with col1: create_audio_button(q.get("word",""), "🔊 單字發音", theme_mode)
        with col2: create_audio_button(q.get("example",""), "📢 例句朗讀", theme_mode)

        if st.button("下一題 ➡️", type="primary", use_container_width=True):
            st.session_state.q = None; st.session_state.state = "q"; st.session_state.count += 1
            st.rerun()

elif mode == "新增單字庫":
    st.title("📝 管理單字庫")
    st.subheader("新增單字內容")
    url = st.secrets["connections"]["gsheets"].get("script_url")
    with st.form("add"):
        w = st.text_input("單字 (Word)")
        d = st.text_input("定義 (Definition)")
        ex = st.text_area("例句 (Example)")
        pt = st.text_area("重點說明 (Point)")
        if st.form_submit_button("確認送出"):
            requests.post(url, json={"method": "write", "word": w, "definition": d, "example": ex, "point": pt})
            st.success("資料已成功上傳至 Google Sheets")
