import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import random
import re
import requests
import base64
import io
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

    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# SESSION SAFE INIT（🔥 修正核心）
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
# 同步
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

# ==============================================================================
# 出題（單字）
# ==============================================================================
def get_weighted_question(user_id, practice_mode):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
    SELECT v.*, IFNULL(p.wrong_count,0) as wrongs, 
           IFNULL(p.correct_streak,0) as streak
    FROM vocabs v
    LEFT JOIN user_progress p
    ON v.id = p.vocab_id AND p.user_id = ?
    """, conn, params=(user_id,))

    if df.empty:
        return None

    if practice_mode == "錯題":
        df = df[df['wrongs'] > 0]
        if df.empty:
            return None

    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)

    target = df.sample(n=1, weights='weight').iloc[0]

    dist = pd.read_sql_query("""
    SELECT word FROM vocabs 
    WHERE pos = ? AND word != ?
    ORDER BY RANDOM() LIMIT 3
    """, conn, params=(target['pos'], target['word']))

    options = dist['word'].tolist() + [target['word']]
    random.shuffle(options)

    conn.close()

    return {
        "id": int(target['id']),
        "word": target['word'],
        "definition": target['definition'],
        "example": target['example'],
        "point": target['point'],
        "pos": target['pos'],
        "options": options,
        "correct": target['word']
    }

# ==============================================================================
# 出題（填空）
# ==============================================================================
def get_cloze_question(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
        SELECT v.*, 
               IFNULL(p.wrong_count,0) as wrongs,
               IFNULL(p.correct_streak,0) as streak
        FROM vocabs v
        LEFT JOIN user_progress p
        ON v.id = p.vocab_id AND p.user_id = ?
        WHERE v.example IS NOT NULL AND v.example != ''
    """, conn, params=(user_id,))

    if df.empty:
        return None

    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)

    target = df.sample(n=1, weights='weight').iloc[0]

    sentence = str(target['example'])
    word = str(target['word'])

    blank_sentence = re.sub(re.escape(word), " ______ ", sentence, flags=re.IGNORECASE)

    dist = pd.read_sql_query("""
        SELECT word FROM vocabs
        WHERE word != ? AND pos = ?
        ORDER BY RANDOM() LIMIT 3
    """, conn, params=(word, target['pos']))

    options = dist['word'].tolist() + [word]
    random.shuffle(options)

    conn.close()

    return {
        "id": int(target["id"]),
        "sentence": blank_sentence,
        "answer": word,
        "options": options,
        "example": sentence,
        "point": target["point"],
        "word": word
    }

# ==============================================================================
# 發音
# ==============================================================================
def create_audio_button(text, button_text, theme_mode):
    if not text:
        return

    clean_text = re.sub(r'[^a-zA-Z0-9\s\.,?!]', '', text)

    try:
        tts = gTTS(text=clean_text, lang='en')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        audio_base64 = base64.b64encode(mp3_fp.getvalue()).decode()

        bg_color = "#262730" if theme_mode == "深色" else "#F0F2F6"
        text_color = "white" if theme_mode == "深色" else "#31333F"

        html_code = f"""
        <audio id="audio_player" src="data:audio/mp3;base64,{audio_base64}"></audio>
        <button onclick="document.getElementById('audio_player').play()"
        style="width:100%;padding:10px;border-radius:10px;
        background:{bg_color};color:{text_color};border:none;">
        {button_text}
        </button>
        """
        components.html(html_code, height=50)

    except:
        st.warning("發音失敗")

# ==============================================================================
# Sidebar
# ==============================================================================
st.sidebar.title("設定")

user_id = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("模式", ["測驗", "新增單字庫"])
practice_mode = st.sidebar.selectbox("練習模式", ["單字", "填空", "錯題"])
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

# ==============================================================================
# INIT SESSION
# ==============================================================================
init_session()

# 🔥 新增修正：當練習模式切換時，強制清除上一題，讓克漏字題型能順利載入
if "last_practice_mode" not in st.session_state:
    st.session_state.last_practice_mode = practice_mode

if st.session_state.last_practice_mode != practice_mode:
    st.session_state.q = None
    st.session_state.state = "q"
    st.session_state.last_practice_mode = practice_mode

# ==============================================================================
# CSS (🔥 修正顏色連動與看不見的問題)
# ==============================================================================
if theme_mode == "深色":
    app_bg = "#0E1117"
    sidebar_bg = "#262730"
    text_col = "white"
    card_bg = "#111827"
    border_col = "rgba(255,255,255,0.2)"
else:
    app_bg = "#F0F2F6"
    sidebar_bg = "#FFFFFF"
    text_col = "#111827"
    card_bg = "#FFFFFF"
    border_col = "rgba(0,0,0,0.2)"

st.markdown(f"""
<style>
/* 強制設定背景，避免預設主題衝突 */
.stApp {{ background-color: {app_bg} !important; }}
section[data-testid="stSidebar"] {{ background-color: {sidebar_bg} !important; }}

/* 強制文字顏色，讓淺色模式左邊設定項目清晰 */
h1, h2, h3, p, label, span {{ color: {text_col} !important; }}

/* 題目卡片設計 */
.card {{
    background: {card_bg};
    padding: 25px;
    border-radius: 20px;
    text-align: center;
    margin-bottom: 20px;
    border: 1px solid {border_col};
}}
.big {{ font-size: 24px; color: {text_col} !important; font-weight: bold; }}

/* 修正右邊四個選項按鈕可見度 */
.stButton>button {{
    color: {text_col} !important;
    border: 1px solid {border_col} !important;
    background-color: {card_bg} !important;
}}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 主流程
# ==============================================================================
if mode == "測驗":

    if not user_id:
        st.warning("請輸入User ID")
        st.stop()

    TOTAL = 10

    # 出題
    if st.session_state.q is None:

        if practice_mode == "填空":
            st.session_state.q = get_cloze_question(user_id)
        else:
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q

    if q is None:
        st.warning("目前沒有題目")
        st.stop()

    # progress（🔥 safe）
    st.progress(min(st.session_state.get("count", 1) / TOTAL, 1.0))

    st.markdown(f"🏆 {st.session_state.score}　🔥 {st.session_state.streak}")

    display_text = q.get("sentence", q.get("definition", ""))

    st.markdown(f"""
    <div class="card">
        <div class="big">{display_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # 作答
    if st.session_state.state == "q":

        for opt in q["options"]:
            if st.button(opt):
                st.session_state.selected = opt
                st.session_state.state = "result"
                st.rerun()

    else:

        correct = q.get("answer") or q.get("correct")
        selected = st.session_state.selected
        is_correct = selected == correct

        if not is_correct:
            st.session_state.wrong_list.append(q)

        if is_correct:
            st.success("✅ Correct")
            st.session_state.score += 10
            st.session_state.streak += 1
        else:
            st.error(f"❌ {correct}")

        st.markdown("### 📌 解析")
        st.write(q.get("example", ""))
        st.write(q.get("point", ""))

        col1, col2 = st.columns(2)
        with col1:
            create_audio_button(q.get("word",""), "🔊 單字", theme_mode)
        with col2:
            create_audio_button(q.get("example",""), "📢 例句", theme_mode)

        if st.button("下一題"):

            st.session_state.q = None
            st.session_state.state = "q"
            st.session_state.count += 1
            st.rerun()

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
