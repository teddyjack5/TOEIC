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
# 1. 基礎設定與 UI 美化
# ==============================================================================
st.set_page_config(page_title="小鐵的多益 Pro 訓練營", page_icon="🚀", layout="centered")

def apply_custom_style(theme):
    if theme == "深色":
        bg_gradient = "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)"
        card_bg = "rgba(255, 255, 255, 0.05)"
        text_color = "#f8fafc"
    else:
        bg_gradient = "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)"
        card_bg = "rgba(255, 255, 255, 0.7)"
        text_color = "#1e293b"

    st.markdown(f"""
    <style>
    .stApp {{
        background: {bg_gradient};
    }}
    .quiz-card {{
        background: {card_bg};
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 35px;
        border-radius: 24px;
        text-align: center;
        margin: 10px 0px 25px 0px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }}
    .english-text {{
        font-size: 26px;
        font-weight: 600;
        color: {text_color};
        line-height: 1.5;
        margin-bottom: 10px;
    }}
    .pos-tag {{
        color: #ef4444;
        font-weight: bold;
        font-size: 14px;
        text-transform: uppercase;
    }}
    .banner-img {{
        width: 100%;
        height: 180px;
        object-fit: cover;
        border-radius: 18px;
        margin-bottom: 15px;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. 資料庫與同步邏輯
# ==============================================================================
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
    c.execute('''CREATE TABLE IF NOT EXISTS system_config 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def sync_data():
    try:
        conn_gs = st.connection("gsheets", type=GSheetsConnection)
        df_gs = conn_gs.read()
        conn_db = sqlite3.connect(DB_NAME)
        for _, row in df_gs.iterrows():
            conn_db.execute('''INSERT OR REPLACE INTO vocabs 
            (word, pos, definition, example, point)
            VALUES (?, ?, ?, ?, ?)''', 
            (str(row['word']), str(row['pos']), str(row['definition']), str(row['example']), str(row['point'])))
        conn_db.commit()
        conn_db.close()
        return True
    except:
        return False

def auto_sync_check():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM system_config WHERE key = 'last_sync'")
    res = c.fetchone()
    today = datetime.date.today()
    
    if res is None or (today - datetime.datetime.strptime(res[0], '%Y-%m-%d').date()).days >= 10:
        if sync_data():
            c.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('last_sync', ?)", (today.isoformat(),))
            conn.commit()
            st.sidebar.info("💡 已自動同步雲端單字庫")
    conn.close()

# ==============================================================================
# 3. 核心功能：出題與發音
# ==============================================================================
def get_question(user_id, practice_mode):
    conn = sqlite3.connect(DB_NAME)
    sql = """
    SELECT v.*, IFNULL(p.wrong_count,0) as wrongs, IFNULL(p.correct_streak,0) as streak
    FROM vocabs v
    LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?
    """
    if practice_mode == "填空":
        sql += " WHERE v.example IS NOT NULL AND v.example != '' AND v.example != 'nan'"
    elif practice_mode == "錯題":
        sql += " WHERE p.wrong_count > 0"

    df = pd.read_sql_query(sql, conn, params=(user_id,))
    if df.empty:
        conn.close()
        return None

    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)
    target = df.sample(n=1, weights='weight').iloc[0]

    # 抓取干擾項 (同詞性優先)
    dist = pd.read_sql_query("SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3", 
                             conn, params=(target['word'],))
    options = dist['word'].tolist() + [target['word']]
    random.shuffle(options)
    conn.close()

    return {
        "id": int(target['id']),
        "word": str(target['word']),
        "definition": str(target['definition']),
        "example": str(target['example']),
        "point": str(target['point']),
        "pos": str(target['pos']),
        "options": options,
        "cloze_text": re.sub(re.escape(str(target['word'])), " ______ ", str(target['example']), flags=re.IGNORECASE)
    }

def create_audio_button(text, button_text, theme_mode):
    if not text or text == "nan": return
    clean_text = re.sub(r'[^a-zA-Z0-9\s\.,?!]', '', text)
    try:
        tts = gTTS(text=clean_text, lang='en')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        audio_base64 = base64.b64encode(mp3_fp.getvalue()).decode()
        bg = "#334155" if theme_mode == "深色" else "#cbd5e1"
        fg = "white" if theme_mode == "深色" else "#1e293b"
        html = f"""
        <audio id="aud" src="data:audio/mp3;base64,{audio_base64}"></audio>
        <button onclick="document.getElementById('aud').play()" 
        style="width:100%;padding:12px;border-radius:12px;background:{bg};color:{fg};border:none;cursor:pointer;font-weight:600;">
        {button_text}
        </button>
        """
        components.html(html, height=55)
    except: pass

# ==============================================================================
# 4. 主程式介面邏輯
# ==============================================================================
init_db()

with st.sidebar:
    st.title("🚀 多益 Pro 控制台")
    user_id = st.text_input("識別碼 (User ID)", value="Guest")
    practice_mode = st.selectbox("模式選擇", ["單字模式", "填空模式", "錯題複習"])
    theme_mode = st.radio("主題視覺", ["深色", "淺色"], horizontal=True)
    if st.button("🔄 手動同步單字庫"):
        if sync_data(): st.success("同步成功")
    st.divider()
    st.caption("學習紀錄會自動儲存在本地資料庫中。")

apply_custom_style(theme_mode)
auto_sync_check()

if "q" not in st.session_state: st.session_state.q = None
if "answered" not in st.session_state: st.session_state.answered = False

# 測驗邏輯
if st.session_state.q is None:
    st.session_state.q = get_question(user_id, practice_mode.split("模式")[0])
    st.session_state.answered = False

q = st.session_state.q

if q:
    # 隨機插圖提升美感 (Unsplash 隨機圖)
    st.markdown(f'<img src="https://images.unsplash.com/photo-1544652478-6653e09f18a2?auto=format&fit=crop&w=800&q=60" class="banner-img">', unsafe_allow_html=True)
    
    # 決定顯示內容：填空模式不顯示中文
    display_title = q['cloze_text'] if "填空" in practice_mode else q['definition']
    
    st.markdown(f"""
    <div class="quiz-card">
        <div class="pos-tag">{q['pos']}</div>
        <div class="english-text">{display_title}</div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(2)
    for i, opt in enumerate(q['options']):
        with cols[i % 2]:
            if st.button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.answered):
                st.session_state.answered = True
                st.session_state.last_pick = opt
                # 更新 SQLite
                conn = sqlite3.connect(DB_NAME)
                is_correct = (opt == q['word'])
                if is_correct:
                    conn.execute("INSERT INTO user_progress (user_id, vocab_id, correct_streak, last_tested) VALUES (?, ?, 1, CURRENT_TIMESTAMP) ON CONFLICT(user_id, vocab_id) DO UPDATE SET correct_streak=correct_streak+1, last_tested=CURRENT_TIMESTAMP", (user_id, q['id']))
                else:
                    conn.execute("INSERT INTO user_progress (user_id, vocab_id, wrong_count, correct_streak, last_tested) VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP) ON CONFLICT(user_id, vocab_id) DO UPDATE SET wrong_count=wrong_count+1, correct_streak=0, last_tested=CURRENT_TIMESTAMP", (user_id, q['id']))
                conn.commit()
                conn.close()
                st.rerun()

    if st.session_state.answered:
        if st.session_state.last_pick == q['word']:
            st.success("🎯 太棒了！回答正確")
        else:
            st.error(f"❌ 答錯囉！正確答案是：{q['word']}")

        with st.expander("📖 查看詳細解析與發音", expanded=True):
            st.write(f"**單字解說：** {q['point']}")
            st.write(f"**完整例句：** {q['example']}")
            vcol1, vcol2 = st.columns(2)
            with vcol1: create_audio_button(q['word'], "🔊 單字發音", theme_mode)
            with vcol2: create_audio_button(q['example'], "📢 例句發音", theme_mode)
        
        if st.button("下一題 ➡️", type="primary", use_container_width=True):
            st.session_state.q = None
            st.rerun()
else:
    st.info("目前沒有題目，請確認單字庫是否有資料，或更換練習模式。")

# ==============================================================================
# 新增單字
# ==============================================================================
elif mode == "新增單字庫":

    st.subheader("新增單字")

    url = st.secrets["connections"]["gsheets"].get("script_url")

    with st.form("add"):
        w = st.text_input("word")
        d = st.text_input("definition")
        ex = st.text_area("example")
        pt = st.text_area("point")

        if st.form_submit_button("送出"):
            payload = {"word": w, "definition": d, "example": ex, "point": pt}
            requests.post(url, json=payload)
            st.success("完成")
