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
# 出題（填空）🔥 修正：移除題目中的中文翻譯
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

    full_example = str(target['example'])
    word = str(target['word'])
    
    # 使用正則移除括號及其中的內容 (中文部分)
    pure_english_sentence = re.sub(r'\s*\(.*?\)', '', full_example).strip()

    # 將目標單字換成空格
    blank_sentence = re.sub(re.escape(word), " ______ ", pure_english_sentence, flags=re.IGNORECASE)

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
        "example": full_example, # 解析時仍保留完整例句含中文
        "point": target["point"],
        "word": word
    }

# ==============================================================================
# 發音
# ==============================================================================
def create_audio_button(text, button_text, theme_mode):
    if not text:
        return
    # 移除發音用的中文
    clean_text = re.sub(r'\(.*?\)', '', text)
    clean_text = re.sub(r'[^a-zA-Z0-9\s\.,?!]', '', clean_text)

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
        background:{bg_color};color:{text_color};border:1px solid rgba(128,128,128,0.2);cursor:pointer;">
        {button_text}
        </button>
        """
        components.html(html_code, height=50)
    except:
        st.warning("發音失敗")

# ==============================================================================
# Sidebar & 主題設定
# ==============================================================================
st.sidebar.title("🛠️ 設定")
user_id = st.sidebar.text_input("User ID", value="小鐵")
mode = st.sidebar.radio("模式", ["測驗", "新增單字庫"])
practice_mode = st.sidebar.selectbox("練習模式", ["單字", "填空", "錯題"])
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

# ==============================================================================
# INIT SESSION & 模式切換檢查
# ==============================================================================
init_session()

if "current_practice_mode" not in st.session_state:
    st.session_state.current_practice_mode = practice_mode

# 如果模式切換，強制更新題目
if st.session_state.current_practice_mode != practice_mode:
    st.session_state.q = None
    st.session_state.state = "q"
    st.session_state.current_practice_mode = practice_mode

# ==============================================================================
# CSS 🔥 修正：淺色模式可見度與側邊欄文字
# ==============================================================================
if theme_mode == "深色":
    main_bg = "#0E1117"
    card_bg = "#111827"
    text_color = "#FFFFFF"
    btn_bg = "#262730"
    sidebar_text = "#FFFFFF"
else:
    main_bg = "#FFFFFF"
    card_bg = "#F0F2F6"
    text_color = "#111827"
    btn_bg = "#FFFFFF"
    sidebar_text = "#111827"

st.markdown(f"""
<style>
    /* 主背景 */
    .stApp {{ background-color: {main_bg}; }}
    
    /* 側邊欄文字顏色修正 */
    section[data-testid="stSidebar"] {{ color: {sidebar_text}; }}
    section[data-testid="stSidebar"] .stText {{ color: {sidebar_text} !important; }}
    section[data-testid="stSidebar"] label p {{ color: {sidebar_text} !important; }}

    /* 題目卡片 */
    .card {{
        background: {card_bg};
        padding: 30px;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid rgba(128,128,128,0.1);
    }}
    .big {{ font-size: 24px; color: {text_color}; font-weight: bold; }}
    
    /* 按鈕顏色連動修正 */
    .stButton>button {{
        color: {text_color} !important;
        background-color: {btn_bg} !important;
        border: 1px solid rgba(128,128,128,0.3) !important;
    }}
    
    /* 積分文字 */
    .status-text {{ color: {text_color}; font-weight: bold; }}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 主流程
# ==============================================================================
if mode == "測驗":
    if not user_id:
        st.warning("請輸入User ID")
        st.stop()

    st.title("🚀 TOEIC Pro 學習助手")
    TOTAL = 10

    # 出題邏輯
    if st.session_state.q is None:
        if practice_mode == "填空":
            st.session_state.q = get_cloze_question(user_id)
        else:
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q
    if q is None:
        st.info("目前沒有符合條件的題目，請嘗試切換練習模式或同步單字。")
        st.stop()

    # 進度條
    st.progress(min(st.session_state.count / TOTAL, 1.0))
    st.markdown(f"<div class='status-text'>🏆 積分：{st.session_state.score}　🔥 連勝：{st.session_state.streak}</div>", unsafe_allow_html=True)

    # 顯示題目
    display_text = q.get("sentence", q.get("definition", ""))
    st.markdown(f"""<div class="card"><div class="big">{display_text}</div></div>""", unsafe_allow_html=True)

    # 作答區
    if st.session_state.state == "q":
        cols = st.columns(2)
        for i, opt in enumerate(q["options"]):
            with cols[i % 2]:
                if st.button(opt, use_container_width=True, key=f"opt_{i}"):
                    st.session_state.selected = opt
                    st.session_state.state = "result"
                    st.rerun()
    else:
        # 結果顯示
        correct = q.get("answer") or q.get("correct")
        selected = st.session_state.selected
        is_correct = (selected == correct)

        if is_correct:
            st.success("✅ Correct! 太棒了！")
            if st.session_state.state == "result": # 避免重複加分
                st.session_state.score += 10
                st.session_state.streak += 1
                st.session_state.state = "done" # 標記已處理
        else:
            st.error(f"❌ 錯誤。正確答案是：{correct}")
            st.session_state.streak = 0

        # 解析區
        with st.expander("📌 深度解析", expanded=True):
            st.write(f"**完整例句：** {q.get('example', '')}")
            st.write(f"**重點考點：** {q.get('point', '')}")
            
            c1, c2 = st.columns(2)
            with c1:
                create_audio_button(q.get("word",""), "🔊 單字發音", theme_mode)
            with c2:
                create_audio_button(q.get("example",""), "📢 例句發音", theme_mode)

        if st.button("下一題 ➡️", type="primary", use_container_width=True):
            st.session_state.q = None
            st.session_state.state = "q"
            st.session_state.count += 1
            st.rerun()

elif mode == "新增單字庫":
    st.title("📝 管理單字庫")
    url = st.secrets["connections"]["gsheets"].get("script_url")

    with st.form("add_vocab"):
        w = st.text_input("單字 (word)")
        d = st.text_input("定義 (definition)")
        ex = st.text_area("例句 (example) - 建議格式: English sentence (中文翻譯)")
        pt = st.text_area("考點說明 (point)")
        
        if st.form_submit_button("新增至資料庫"):
            if w and d:
                payload = {"word": w, "definition": d, "example": ex, "point": pt}
                try:
                    requests.post(url, json=payload)
                    st.success(f"單字 '{w}' 已成功送出！")
                except:
                    st.error("連線至 Google Sheets 失敗。")
            else:
                st.warning("請填寫單字與定義。")
