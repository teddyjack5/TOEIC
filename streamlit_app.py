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
    
    if df.empty: 
        conn.close()
        return None

    # 高手加權演算法
    df['weight'] = 1 + (df['wrongs'] * 5) - (df['streak'] * 1.5)
    df['weight'] = df['weight'].clip(lower=0.1)
    
    # 填空模式過濾 (確保有例句)
    if "Cloze" in mode_type:
        df = df[df['example'].str.len() > 5]
        if df.empty: # 如果沒有單字有例句，退回普通模式
            df = pd.read_sql_query(query, conn, params=(user_id,))

    target = df.sample(n=1, weights='weight').iloc[0]
    
    # --- 關鍵修正區：抓取誘答選項 (Distractors) ---
    # 不論模式，我們都先抓出正確答案的「欄位值」
    is_standard = "標準選擇題" in mode_type
    target_col = 'definition' if is_standard else 'word'
    correct_ans = str(target[target_col])

    # 改用更穩定的方式抓取其他選項
    dist_col = 'definition' if is_standard else 'word'
    dist_query = f"SELECT {dist_col} FROM vocabs WHERE word != ? ORDER BY RANDOM() LIMIT 3"
    
    try:
        dist_df = pd.read_sql_query(dist_query, conn, params=(target['word'],))
        # 直接取第一欄的所有值，避免字串比對 Key 的問題
        distractors = dist_df.iloc[:, 0].astype(str).tolist()
    except Exception as e:
        distractors = []

    conn.close()
    
    # 確保至少有選項，即使庫太小也不會崩潰
    while len(distractors) < 3:
        distractors.append(" (候選選項不足) ")

    options = distractors + [correct_ans]
    random.shuffle(options)
    
    cloze_text = ""
    if "Cloze" in mode_type and target['example']:
        # 忽略大小寫的替換
        pattern = re.compile(re.escape(target['word']), re.IGNORECASE)
        cloze_text = pattern.sub(" _______ ", str(target['example']))

    return {
        'id': int(target['id']), 
        'word': str(target['word']), 
        'pos': str(target['pos']),
        'correct_ans': correct_ans,
        'options': options, 
        'example': str(target['example']), 
        'point': str(target['point']),
        'cloze_text': cloze_text
    }

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
    
    # 這裡定義 mode，後續的 if/elif 必須對應這裡的選項
    mode = st.radio("🚀 功能模式切換", ["開始測驗", "新增單字庫"])
    
    quiz_mode = st.selectbox("📝 測驗題型", ["標準選擇題", "填空挑戰 (Cloze)"])
    
    if st.button("🔄 同步雲端單字庫"):
        if sync_data(): st.success("同步成功！")
    
    if st.button("🗑️ 重置我的紀錄"):
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        st.rerun()

st.title(f"📖 {user_id} 的多益訓練營")

# --- 模式 1：開始測驗 ---
if mode == "開始測驗":
    # 初始化狀態
    if 'q' not in st.session_state: st.session_state.q = None
    if 'answered' not in st.session_state: st.session_state.answered = False

    # 觸發抽題
    if st.session_state.q is None:
        st.session_state.q = get_weighted_question(user_id, quiz_mode)
        st.session_state.answered = False
        st.rerun() # 強制重新整理確保狀態同步

    q = st.session_state.q

    if q:
        # 顯示單字
        st.markdown(f"""
            <div style="background-color:#1E2E44; padding:30px; border-radius:15px; text-align:center;">
                <h1 style="color:white;">{q['word'] if quiz_mode == "標準選擇題" else q['cloze_text']}</h1>
                <p style="color:#FF4B4B;">({q['pos']})</p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")

cols = st.columns(2)
        for i, opt in enumerate(q['options']):
            with cols[i % 2]:
                # 關鍵點：使用唯一的 key，並在點擊時進行類型轉換
                if st.button(opt, key=f"btn_{q['id']}_{i}", use_container_width=True, disabled=st.session_state.answered):
                    # 1. 立即標記已回答，防止重複觸發
                    st.session_state.answered = True
                    
                    # 2. 判定對錯
                    is_correct = bool(opt == q['correct_ans'])
                    st.session_state.last_result = is_correct
                    
                    # 3. 安全更新資料庫 (強制轉型避免 SQLite 報錯)
                    # 確保 q['id'] 傳進去的是原生 int，而不是 numpy.int64
                    try:
                        vocab_id_int = int(q['id'])
                        update_progress(user_id, vocab_id_int, is_correct)
                    except Exception as e:
                        st.error(f"進度更新失敗: {e}")
                    
                    # 4. 重新渲染頁面以顯示結果
                    st.rerun()

        # 答題後的結果與解析
        if st.session_state.answered:
            if st.session_state.last_result:
                st.success("🎯 Correct!")
            else:
                st.error(f"❌ Wrong! Answer: {q['correct_ans']}")
            
            # --- 解析區塊 (展開解析) ---
            with st.expander("🔍 查看解析與重點", expanded=True):
                if q['point'] and str(q['point']) != 'nan':
                    st.info(f"📌 重點：{q['point']}")
                if q['example'] and str(q['example']) != 'nan':
                    st.write(f"💡 例句：{q['example']}")
            
            # 下一題按鈕
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                # 清空當前題目狀態，下一次重整時會自動觸發 get_weighted_question
                st.session_state.q = None
                st.session_state.answered = False
                st.rerun()

# --- 模式 2：新增單字庫 (修正 SyntaxError 的關鍵區塊) ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    # 注意：這裡的 URL 必須在 secrets.toml 裡面有定義 script_url
    url = st.secrets["connections"]["gsheets"].get("script_url")
    
    if not url:
        st.warning("⚠️ 尚未設定 script_url，無法自動同步回 Google Sheets。請先在 Secrets 中設定。")

    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1: w = st.text_input("英文單字")
        with col2: p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
        
        d = st.text_input("中文定義")
        pt = st.text_area("出題重點 (Point)")
        ex = st.text_area("例句 (Example Sentence)")
        
        if st.form_submit_button("💾 儲存並同步"):
            if w and d and url:
                payload = {
                    "method": "write", "word": w, "pos": p, 
                    "definition": d, "point": pt, "example": ex
                }
                try:
                    res = requests.post(url, json=payload)
                    if res.status_code == 200:
                        st.success(f"✅ 『{w}』已送出！請記得稍後點擊「同步雲端單字庫」。")
                    else:
                        st.error("寫入失敗，請檢查 Google Apps Script 設定。")
                except Exception as e: 
                    st.error(f"連線錯誤：{e}")
            elif not w or not d:
                st.warning("請填寫單字與定義。")
