import streamlit as st
import pandas as pd
import sqlite3
import random
import re
import tempfile
import os
import requests  # 補上這個用於新增單字
from gtts import gTTS
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# ==============================================================================
# 1. 初始化與資料庫設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益 Pro 學習系統", page_icon="🚀", layout="wide")

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
# 2. 資料庫操作 (更新進度) - 補回缺失的函式
# ==============================================================================
def update_progress(user_id, vocab_id, is_correct):
    conn = sqlite3.connect(DB_NAME, timeout=10)
    try:
        c = conn.cursor()
        if is_correct:
            c.execute('''INSERT INTO user_progress (user_id, vocab_id, correct_streak, last_tested)
                         VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                         ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
                         correct_streak = correct_streak + 1, last_tested = CURRENT_TIMESTAMP''', (user_id, vocab_id))
        else:
            c.execute('''INSERT INTO user_progress (user_id, vocab_id, wrong_count, correct_streak, last_tested)
                         VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
                         ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
                         wrong_count = wrong_count + 1, correct_streak = 0, last_tested = CURRENT_TIMESTAMP''', (user_id, vocab_id))
        conn.commit()
    finally:
        conn.close()

# ==============================================================================
# 3. 資料同步與核心邏輯
# ==============================================================================
def sync_data():
    try:
        conn_gs = st.connection("gsheets", type=GSheetsConnection)
        df_gs = conn_gs.read()
        conn_db = sqlite3.connect(DB_NAME)
        for _, row in df_gs.iterrows():
            conn_db.execute('''INSERT OR REPLACE INTO vocabs (word, pos, definition, example, point)
                               VALUES (?, ?, ?, ?, ?)''', (row['word'], row['pos'], row['definition'], row['example'], row['point']))
        conn_db.commit()
        conn_db.close()
        return True
    except Exception as e:
        st.error(f"同步失敗: {e}")
        return False

def get_weighted_question(user_id, mode_type):
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT v.*, IFNULL(p.wrong_count, 0) as wrongs, IFNULL(p.correct_streak, 0) as streak FROM vocabs v LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?"
    df = pd.read_sql_query(query, conn, params=(user_id,))
    if df.empty: 
        conn.close()
        return None

    df['weight'] = 1 + (df['wrongs'] * 5) - (df['streak'] * 1.5)
    df['weight'] = df['weight'].clip(lower=0.1)
    
    if "Cloze" in mode_type:
        df = df[df['example'].str.len() > 5]
        if df.empty: df = pd.read_sql_query(query, conn, params=(user_id,))

    target = df.sample(n=1, weights='weight').iloc[0]
    is_standard = "標準選擇題" in mode_type
    target_col = 'definition' if is_standard else 'word'
    correct_ans = str(target[target_col])

    dist_query = f"SELECT {'definition' if is_standard else 'word'} FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3"
    dist_df = pd.read_sql_query(dist_query, conn, params=(target['word'],))
    distractors = dist_df.iloc[:, 0].astype(str).tolist()
    conn.close()

    while len(distractors) < 3: distractors.append(" (選項不足) ")
    options = distractors + [correct_ans]
    random.shuffle(options)
    
    cloze_text = ""
    if "Cloze" in mode_type and target['example']:
        pattern = re.compile(re.escape(target['word']), re.IGNORECASE)
        cloze_text = pattern.sub(" _______ ", str(target['example']))

    return {'id': int(target['id']), 'word': str(target['word']), 'pos': str(target['pos']),
            'correct_ans': correct_ans, 'options': options, 'example': str(target['example']), 
            'point': str(target['point']), 'cloze_text': cloze_text}

def speak(text):
    if not text or str(text) == 'nan': return
    clean_text = " ".join(re.findall(r'[a-zA-Z0-9\s\.,\?!\']+', text))
    tts = gTTS(text=clean_text, lang='en')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        st.audio(f.name, format="audio/mp3", autoplay=True)

# ==============================================================================
# 4. 主程式介面
# ==============================================================================
with st.sidebar:
    st.title("⚙️ 控制面板")
    user_id = st.text_input("👤 使用者識別 (ID)", value="", placeholder="請輸入您的名稱...")

    st.header("🎨 介面設定")
    theme_mode = st.radio("主題模式", ["深色", "淺色"], horizontal=True)
    quiz_mode = st.selectbox("📝 測驗題型", ["標準選擇題", "填空挑戰 (Cloze)"], key="main_quiz_mode")
    
    if st.button("🔄 同步雲端單字庫"):
        if sync_data(): st.success("同步成功！")
    
    if st.button("🗑️ 重置我的紀錄"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        st.rerun()

# 注入簡單主題 CSS
if theme_mode == "深色":
    st.markdown("""
        <style>
        /* 1. 全域背景與文字 */
        .stApp { 
            background-color: #0E1117; 
            color: white; 
        }
        
        /* 2. 強制修改所有按鈕的樣式 (解決選項看不見的問題) */
        div.stButton > button {
            background-color: #262730 !important; /* 深灰色背景 */
            color: #FFFFFF !important;           /* 純白文字 */
            border: 1px solid #4B4B4B !important; /* 灰色邊框 */
        }
        
        /* 3. 答題後的正確/錯誤訊息文字顏色優化 */
        .stSuccess, .stError {
            color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)
else:
    # 淺色模式維持預設，或稍微優化
    st.markdown("""
        <style>
        div.stButton > button {
            border: 1px solid #DDE4ED !important;
        }
        </style>
    """, unsafe_allow_html=True)

st.title(f"📖 {user_id if user_id else '訪客'} 的多益訓練營")

if not user_id.strip():
    st.warning("👋 歡迎！請先在左側控制面板輸入您的「使用者識別 ID」。")
    st.stop()

# --- 模式 1：開始測驗 ---
if mode == "開始測驗":
    if 'q' not in st.session_state: st.session_state.q = None
    if 'answered' not in st.session_state: st.session_state.answered = False

    if st.session_state.q is None:
        st.session_state.q = get_weighted_question(user_id, quiz_mode)
        st.session_state.answered = False
        st.rerun()

    q = st.session_state.q
    if q:
        # 決定要顯示的文字：如果是填空模式就顯示 cloze_text，否則顯示單字
        display_text = q['cloze_text'] if "Cloze" in quiz_mode else q['word']
        
        # 如果是填空模式但 cloze_text 竟然是空的，強制補回單字避免畫面空白
        if not display_text or display_text.strip() == "":
            display_text = q['word']

        st.markdown(f"""
            <div style="background-color:#1E2E44; padding:30px; border-radius:15px; text-align:center;">
                <h1 style="color:white;">{display_text}</h1>
                <p style="color:#FF4B4B;">({q['pos']})</p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")

        cols = st.columns(2)
        for i, opt in enumerate(q['options']):
            with cols[i % 2]:
                if st.button(opt, key=f"btn_{q['id']}_{i}", use_container_width=True, disabled=st.session_state.answered):
                    st.session_state.answered = True
                    is_correct = bool(opt == q['correct_ans'])
                    st.session_state.last_result = is_correct
                    update_progress(user_id, q['id'], is_correct)
                    st.rerun()

        if st.session_state.answered:
            if st.session_state.last_result: st.success("🎯 Correct!")
            else: st.error(f"❌ Wrong! Answer: {q['correct_ans']}")

            with st.expander("🔍 查看解析與發音", expanded=True):
                vcol1, vcol2 = st.columns(2)
                with vcol1:
                    if st.button("🔊 單字發音", key=f"v_{q['id']}"): speak(q['word'])
                with vcol2:
                    if q['example'] != 'nan':
                        if st.button("📢 例句發音", key=f"e_{q['id']}"): speak(q['example'])
                
                if q['point'] != 'nan': st.info(f"📌 重點：{q['point']}")
                if q['example'] != 'nan': st.write(f"💡 例句：{q['example']}")
            
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                st.session_state.q = None
                st.session_state.answered = False
                st.rerun()

# --- 模式 2：新增單字庫 ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    url = st.secrets["connections"]["gsheets"].get("script_url")
    if not url: st.warning("⚠️ 尚未設定 script_url")

    with st.form("add_form", clear_on_submit=True):
        w = st.text_input("英文單字")
        p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
        d = st.text_input("中文定義")
        pt = st.text_area("出題重點 (Point)")
        ex = st.text_area("例句 (Example Sentence)")
        
        if st.form_submit_button("💾 儲存並同步"):
            if w and d and url:
                payload = {"method": "write", "word": w, "pos": p, "definition": d, "point": pt, "example": ex}
                res = requests.post(url, json=payload)
                if res.status_code == 200: st.success(f"✅ 『{w}』已送出！")
                else: st.error("寫入失敗")
