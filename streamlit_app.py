import streamlit as st
import pandas as pd
import sqlite3
import random
import re
import tempfile
import os
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
    # 單字主表 (從 GSheets 同步過來)
    c.execute('''CREATE TABLE IF NOT EXISTS vocabs 
                 (id INTEGER PRIMARY KEY, word TEXT UNIQUE, pos TEXT, 
                  definition TEXT, example TEXT, point TEXT)''')
    # 使用者進度表
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress 
                 (user_id TEXT, vocab_id INTEGER, wrong_count INTEGER DEFAULT 0, 
                  correct_streak INTEGER DEFAULT 0, last_tested TIMESTAMP,
                  PRIMARY KEY (user_id, vocab_id))''')
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. 資料同步 (GSheets -> SQLite)
# ==============================================================================
def sync_data():
    try:
        conn_gs = st.connection("gsheets", type=GSheetsConnection)
        df_gs = conn_gs.read()
        
        conn_db = sqlite3.connect(DB_NAME)
        # 僅更新單字庫，不影響進度
        for _, row in df_gs.iterrows():
            conn_db.execute('''
                INSERT OR REPLACE INTO vocabs (word, pos, definition, example, point)
                VALUES (?, ?, ?, ?, ?)
            ''', (row['word'], row['pos'], row['definition'], row['example'], row['point']))
        conn_db.commit()
        conn_db.close()
        return True
    except Exception as e:
        st.error(f"同步失敗: {e}")
        return False

# ==============================================================================
# 3. 核心邏輯：加權抽題與進度更新
# ==============================================================================
def get_weighted_question(user_id, mode_type):
    conn = sqlite3.connect(DB_NAME)
    query = """
        SELECT v.*, IFNULL(p.wrong_count, 0) as wrongs, IFNULL(p.correct_streak, 0) as streak
        FROM vocabs v
        LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    
    if df.empty: return None

    # 高手加權演算法
    # 權重 = 1 (基礎) + 錯誤次數加成 - 連續對次數扣減
    df['weight'] = 1 + (df['wrongs'] * 5) - (df['streak'] * 1.5)
    df['weight'] = df['weight'].clip(lower=0.1) # 確保至少有極小機率出現
    
    # 填空模式過濾
    if mode_type == "填空挑戰 (Cloze)":
        df = df[df['example'].str.len() > 5]

    target = df.sample(n=1, weights='weight').iloc[0]
    
    # 準備選項 (隨機從庫中抓 3 個非正確答案)
    conn = sqlite3.connect(DB_NAME)
    distractors_query = "SELECT definition FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3"
    if mode_type == "填空挑戰 (Cloze)":
        distractors_query = "SELECT word FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3"
    
    distractors = pd.read_sql_query(distractors_query, conn, params=(target['word'],))['definition' if mode_type == "標準選擇題" else 'word'].tolist()
    conn.close()
    
    options = distractors + [target['definition' if mode_type == "標準選擇題" else 'word']]
    random.shuffle(options)
    
    cloze_text = ""
    if mode_type == "填空挑戰 (Cloze)":
        pattern = re.compile(re.escape(target['word']), re.IGNORECASE)
        cloze_text = pattern.sub(" _______ ", target['example'])

    return {
        'id': target['id'], 'word': target['word'], 'pos': target['pos'],
        'correct_ans': target['definition' if mode_type == "標準選擇題" else 'word'],
        'options': options, 'example': target['example'], 'point': target['point'],
        'cloze_text': cloze_text
    }

def update_progress(user_id, vocab_id, is_correct):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if is_correct:
        c.execute('''INSERT INTO user_progress (user_id, vocab_id, correct_streak, last_tested)
                     VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                     ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
                     correct_streak = correct_streak + 1, last_tested = CURRENT_TIMESTAMP''')
    else:
        c.execute('''INSERT INTO user_progress (user_id, vocab_id, wrong_count, correct_streak, last_tested)
                     VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
                     ON CONFLICT(user_id, vocab_id) DO UPDATE SET 
                     wrong_count = wrong_count + 1, correct_streak = 0, last_tested = CURRENT_TIMESTAMP''')
    conn.commit()
    conn.close()

# ==============================================================================
# 4. UI 輔助函數
# ==============================================================================
def speak(text):
    if not text: return
    clean_text = " ".join(re.findall(r'[a-zA-Z0-9\s\.,\?!\']+', text))
    tts = gTTS(text=clean_text, lang='en')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        st.audio(f.name, format="audio/mp3", autoplay=True)

# ==============================================================================
# 5. 主程式介面
# ==============================================================================
with st.sidebar:
    st.title("⚙️ 控制面板")
    user_id = st.text_input("👤 使用者識別 (ID)", value="小鐵")
    quiz_mode = st.selectbox("📝 測驗題型", ["標準選擇題", "填空挑戰 (Cloze)"])
    
    if st.button("🔄 同步雲端單字庫"):
        if sync_data(): st.success("同步成功！")
    
    if st.button("🗑️ 重置我的紀錄"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        st.rerun()

# 狀態初始化
if 'q' not in st.session_state: st.session_state.q = None
if 'answered' not in st.session_state: st.session_state.answered = False

st.title(f"📖 {user_id} 的多益訓練營")

# 抽題邏輯
if st.session_state.q is None:
    st.session_state.q = get_weighted_question(user_id, quiz_mode)
    st.session_state.answered = False

q = st.session_state.q

if q:
    # 顯示題目卡片
    st.markdown(f"""
        <div style="background-color:#1E2E44; padding:30px; border-radius:15px; text-align:center; border:1px solid #4A90E2;">
            <h1 style="color:white; margin:0;">{q['word'] if quiz_mode == "標準選擇題" else q['cloze_text']}</h1>
            <p style="color:#FF4B4B; font-weight:bold;">({q['pos']})</p>
        </div>
    """, unsafe_allow_html=True)
    st.write("")

    # 選項按鈕
    cols = st.columns(2)
    for i, opt in enumerate(q['options']):
        with cols[i % 2]:
            if st.button(opt, key=f"opt_{i}", use_container_width=True, disabled=st.session_state.answered):
                st.session_state.answered = True
                is_correct = (opt == q['correct_ans'])
                update_progress(user_id, q['id'], is_correct)
                st.session_state.last_result = is_correct
                st.rerun()

    # 答題後回饋
    if st.session_state.answered:
        if st.session_state.last_result:
            st.success("🎯 Correct!")
        else:
            st.error(f"❌ Wrong! Answer: {q['correct_ans']}")
        
        # 補充資訊與發音
        with st.expander("🔍 查看解析與發音", expanded=True):
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔊 單字發音"): speak(q['word'])
            with col_b:
                if q['example'] and st.button("📢 例句發音"): speak(q['example'])
            
            if q['point']: st.info(f"📌 重點：{q['point']}")
            if q['example']: st.write(f"💡 例句：{q['example']}")

        if st.button("➡️ 下一題", type="primary", use_container_width=True):
            st.session_state.q = None
            st.rerun()
else:
    st.info("目前單字庫空空如也，請先點擊側邊欄的同步按鈕！")

# --- 模式 3：新增單字庫 ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    url = st.secrets["connections"]["gsheets"]["script_url"]
    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1: w = st.text_input("英文單字")
        with col2: p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
        
        d = st.text_input("中文定義")
        
        # 新增 point 欄位
        pt = st.text_area("出題重點 (Point)", placeholder="例如：常與介系詞 with 連用...")
        
        ex = st.text_area("例句 (Example Sentence)", placeholder="請輸入此單字的用法例句...")
        
        if st.form_submit_button("💾 儲存並同步"):
            if w and d:
                payload = {
                    "method": "write", 
                    "word": w, 
                    "pos": p, 
                    "definition": d, 
                    "point": pt, 
                    "example": ex
                }
                try:
                    res = requests.post(url, json=payload)
                    if res.status_code == 200:
                        st.success(f"✅ 『{w}』及其例句已送出！")
                        st.cache_data.clear()
                except Exception as e: 
                    st.error(f"錯誤：{e}")
