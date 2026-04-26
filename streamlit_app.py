import streamlit as st
import pandas as pd
import sqlite3
import random
import re
import tempfile
import os
import requests
import base64
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

def sync_data():
    try:
        # 建立與 Google Sheets 的連線
        conn_gs = st.connection("gsheets", type=GSheetsConnection)
        # 讀取試算表資料
        df_gs = conn_gs.read()
        
        if df_gs is None or df_gs.empty:
            st.error("雲端試算表是空的，請檢查內容。")
            return False
            
        conn_db = sqlite3.connect(DB_NAME)
        
        # 逐筆寫入 SQLite 資料庫
        for _, row in df_gs.iterrows():
            try:
                conn_db.execute('''INSERT OR REPLACE INTO vocabs (word, pos, definition, example, point)
                                   VALUES (?, ?, ?, ?, ?)''', 
                                (str(row['word']), str(row['pos']), str(row['definition']), 
                                 str(row['example']), str(row['point'])))
            except KeyError as e:
                st.error(f"試算表欄位名稱錯誤：找不到 {e}。請確保 Google Sheet 第一列包含 word, pos, definition, example, point。")
                conn_db.close()
                return False
                
        conn_db.commit()
        conn_db.close()
        return True
    except Exception as e:
        st.error(f"同步失敗，錯誤訊息: {e}")
        return False
# ==============================================================================
# 2. 資料庫操作 (更新進度)
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
# 3. 核心邏輯
# ==============================================================================
def get_weighted_question(user_id, mode_type):
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT v.*, IFNULL(p.wrong_count, 0) as wrongs, IFNULL(p.correct_streak, 0) as streak FROM vocabs v LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?"
    df = pd.read_sql_query(query, conn, params=(user_id,))
    if df.empty: 
        conn.close()
        return None

    # 加權算法
    df['weight'] = 1 + (df['wrongs'] * 5) - (df['streak'] * 1.5)
    df['weight'] = df['weight'].clip(lower=0.1)
    
    # 填空模式過濾：優先找有例句的單字
    if "Cloze" in mode_type:
        cloze_df = df[df['example'].str.len() > 5]
        if not cloze_df.empty:
            df = cloze_df

    target = df.sample(n=1, weights='weight').iloc[0]
    
    # --- 關鍵修正處 ---
    # 無論什麼模式，正確答案永遠是單字本身 (英文)
    correct_ans = str(target['word'])

    # 干擾項也統一只抓 'word' 欄位 (英文)，不分模式
    dist_query = "SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3"
    dist_df = pd.read_sql_query(dist_query, conn, params=(target['word'],))
    distractors = dist_df.iloc[:, 0].astype(str).tolist()
    conn.close()
    # ------------------

    while len(distractors) < 3: distractors.append(" (選項不足) ")
    options = distractors + [correct_ans]
    random.shuffle(options)
    
    # 處理底線邏輯
    cloze_text = ""
    if target['example'] and str(target['example']) != 'nan':
        pattern = re.compile(re.escape(target['word']), re.IGNORECASE)
        cloze_text = pattern.sub(" _______ ", str(target['example']))

    return {
        'id': int(target['id']), 
        'word': str(target['word']), 
        'pos': str(target['pos']),
        'definition': str(target['definition']), # 確保這裡有包含 definition
        'correct_ans': correct_ans, 
        'options': options, 
        'example': str(target['example']), 
        'point': str(target['point']), 
        'cloze_text': cloze_text
    }
def speak_html(text):
    tts = gTTS(text=text, lang='en')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        with open(f.name, "rb") as audio_file:
            audio_bytes = audio_file.read()
        audio_base64 = base64.b64encode(audio_bytes).decode()
        audio_tag = f'<audio src="data:audio/mp3;base64,{audio_base64}" controls autoplay></audio>'
        st.markdown(audio_tag, unsafe_allow_html=True)

# ==============================================================================
# 4. 主程式介面
# ==============================================================================
with st.sidebar:
    st.title("⚙️ 控制面板")
    user_id = st.text_input("👤 使用者識別 (ID)", value="", placeholder="請輸入您的名稱...")

    st.header("🎨 介面設定")
    theme_mode = st.radio("主題模式", ["深色", "淺色"], horizontal=True)
    quiz_mode = st.selectbox("📝 測驗題型", ["標準選擇題", "填空挑戰 (Cloze)"], key="main_quiz_mode")
    
    # --- 這裡最重要！補上 mode 定義 ---
    mode = st.radio("🚀 功能切換", ["開始測驗", "學習進度分析", "新增單字庫"])
    
    if st.button("🔄 更新雲端單字庫"):
        if sync_data(): st.success("更新成功！")
    
    if st.button("🗑️ 重置我的紀錄"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        st.rerun()

# 注入 CSS
if theme_mode == "深色":
    st.markdown("""<style>
        .stApp { background-color: #0E1117; color: white; }
        div.stButton > button { background-color: #262730 !important; color: white !important; border: 1px solid #4B4B4B !important; }
        .stSuccess, .stError { color: white !important; }
        </style>""", unsafe_allow_html=True)
else:
    st.markdown("<style>div.stButton > button { border: 1px solid #DDE4ED !important; }</style>", unsafe_allow_html=True)

st.title(f"📖 {user_id if user_id else '訪客'} 的多益訓練營")

if not user_id.strip():
    st.warning("👋 歡迎！請先在左側控制面板輸入您的「使用者識別 ID」，並且先點左下方更新單字庫。")
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
        # --- 核心顯示邏輯修改 ---
        is_cloze = "Cloze" in quiz_mode
        
        if is_cloze:
            # 填空模式：顯示有底線的英文句子
            display_text = q['cloze_text'] if q['cloze_text'] else q['word']
        else:
            # 標準模式：顯示中文定義，讓使用者選英文單字
            display_text = q['definition'] 
        # ------------------------

        st.markdown(f"""
            <div style="background-color:#1E2E44; padding:30px; border-radius:15px; text-align:center; margin-bottom:20px;">
                <h1 style="color:white; font-size: 32px;">{display_text}</h1>
                <p style="color:#FF4B4B;">({q['pos']})</p>
            </div>
        """, unsafe_allow_html=True)

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
                    if q['example'] and q['example'] != 'nan':
                        if st.button("📢 例句發音", key=f"e_{q['id']}"): speak(q['example'])
                
                if q['point'] and q['point'] != 'nan': st.info(f"📌 重點：{q['point']}")
                if q['example'] and q['example'] != 'nan': st.write(f"💡 原例句：{q['example']}")
            
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

# --- 模式 3：學習進度分析 ---
elif mode == "學習進度分析":
    st.subheader("📊 我的學習戰報")
    
    conn = sqlite3.connect(DB_NAME)
    # 抓取該使用者的進度數據與單字資訊
    query = """
        SELECT v.word, v.definition, p.wrong_count, p.correct_streak, p.last_tested
        FROM user_progress p
        JOIN vocabs v ON p.vocab_id = v.id
        WHERE p.user_id = ?
        ORDER BY p.wrong_count DESC
    """
    df_progress = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()

    if df_progress.empty:
        st.info("目前還沒有測驗紀錄，快去「開始測驗」挑戰看看吧！")
    else:
        # A. 頂部儀表板
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("已練習單字數", len(df_progress))
        with col2:
            # 假設連續正確 3 次以上算「熟練」
            mastered_count = len(df_progress[df_progress['correct_streak'] >= 3])
            st.metric("精通單字量 (Streak >= 3)", mastered_count)
        with col3:
            total_wrongs = df_progress['wrong_count'].sum()
            st.metric("累計錯誤次數", int(total_wrongs))

        # B. 視覺化圖表 (簡單展示前 10 名「魔王單字」)
        st.write("### 😈 你的十大魔王單字 (錯誤次數最多)")
        top_10_wrong = df_progress.head(10)
        st.bar_chart(data=top_10_wrong, x='word', y='wrong_count', color="#FF4B4B")

        # C. 詳細列表
        with st.expander("詳細單字掌握度清單"):
            # 格式化時間與呈現
            df_display = df_progress.copy()
            df_display.columns = ['單字', '定義', '錯誤次數', '連對次數', '最後測驗時間']
            st.dataframe(df_display, use_container_width=True)
