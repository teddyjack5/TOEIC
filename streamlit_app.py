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
# 更新進度
# ==============================================================================
def update_progress(user_id, vocab_id, is_correct):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if is_correct:
        c.execute('''INSERT INTO user_progress 
        VALUES (?, ?, 0, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
        correct_streak = correct_streak + 1''', (user_id, vocab_id))
    else:
        c.execute('''INSERT INTO user_progress 
        VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
        wrong_count = wrong_count + 1, correct_streak = 0''', (user_id, vocab_id))

    conn.commit()
    conn.close()

# ==============================================================================
# 出題
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

    # 🔥 錯題模式
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
# 發音（iOS適用）
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
practice_mode = st.sidebar.selectbox("練習模式", ["全部", "錯題"])
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

# ==============================================================================
# CSS
# ==============================================================================
st.markdown("""
<style>
.card {
    background:#111827;
    padding:25px;
    border-radius:20px;
    text-align:center;
    margin-bottom:20px;
}
.big {font-size:24px;color:white;}
.stButton button {
    width:100%;
    height:55px;
    font-size:18px;
    border-radius:12px;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 主流程
# ==============================================================================
if mode == "測驗":

    if not user_id:
        st.warning("請輸入User ID")
        st.stop()

    if "state" not in st.session_state:
        st.session_state.state = "q"
        st.session_state.score = 0
        st.session_state.streak = 0
        st.session_state.count = 1
        st.session_state.q = None

    if st.session_state.q is None:
        st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q

    if q is None:
        st.warning("目前沒有題目（可能錯題已清空）")
        st.stop()

    # 進度條
    TOTAL = 10
    st.progress(st.session_state.count / TOTAL)

    st.markdown(f"🏆 {st.session_state.score}　🔥 {st.session_state.streak}")

    # 題目卡片
    st.markdown(f"""
    <div class="card">
        <div class="big">{q['definition']}</div>
    </div>
    """, unsafe_allow_html=True)

    # 作答
    if st.session_state.state == "q":
        for opt in q['options']:
            if st.button(opt):
                st.session_state.selected = opt
                st.session_state.state = "result"
                st.rerun()

    # 結果
    else:
        correct = q['correct']
        selected = st.session_state.selected

        is_correct = selected == correct
        update_progress(user_id, q['id'], is_correct)

        if is_correct:
            st.success("✅ Correct")
            st.session_state.score += 10
            st.session_state.streak += 1
        else:
            st.error(f"❌ {correct}")
            st.session_state.streak = 0

        # 解釋
        st.markdown(f"""
        <div class="card">
            <div style="color:#9CA3AF;">{q['point']}</div><br>
            <div style="color:white;">{q['example']}</div>
        </div>
        """, unsafe_allow_html=True)

        # 發音
        st.markdown("### 🔊 發音")
        col1, col2 = st.columns(2)
        with col1:
            create_audio_button(q['word'], "🔊 單字", theme_mode)
        with col2:
            if q['example']:
                create_audio_button(q['example'], "📢 例句", theme_mode)

        # 下一題
        if st.button("➡️ 下一題"):
            st.session_state.q = get_weighted_question(user_id, practice_mode)
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
