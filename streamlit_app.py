import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sqlite3
import random
import re
import requests
import base64
import io
import plotly.express as px  
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

    conn.commit()
    conn.close()
    try:
        c.execute("ALTER TABLE user_progress ADD COLUMN next_review TIMESTAMP")
    except:
        pass

    try:
        c.execute("ALTER TABLE user_progress ADD COLUMN interval INTEGER DEFAULT 1")
    except:
        pass

    try:
        c.execute("ALTER TABLE user_progress ADD COLUMN ease REAL DEFAULT 2.5")
    except:
        pass

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
    if "recall_input_value" not in st.session_state:
        st.session_state.recall_input_value = ""
    if "recall_state" not in st.session_state:
        st.session_state.recall_state = "question"
    if "recall_input" not in st.session_state:
        st.session_state.recall_input = ""
        
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
# 出題（單字/填空邏輯維持不變）
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
    if df.empty: return None
    if practice_mode == "錯題":
        df = df[df['wrongs'] > 0]
        if df.empty: return None
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
        "id": int(target['id']), "word": target['word'], "definition": target['definition'],
        "example": target['example'], "point": target['point'], "pos": target['pos'],
        "options": options, "correct": target['word']
    }

def get_cloze_question(user_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT v.*, IFNULL(p.wrong_count,0) as wrongs, IFNULL(p.correct_streak,0) as streak
        FROM vocabs v
        LEFT JOIN user_progress p ON v.id = p.vocab_id AND p.user_id = ?
        WHERE v.example IS NOT NULL AND v.example != ''
    """, conn, params=(user_id,))
    
    if df.empty: return None
    
    df['weight'] = 1 + df['wrongs'] * 5 - df['streak'] * 1.5
    df['weight'] = df['weight'].clip(lower=0.1)
    target = df.sample(n=1, weights='weight').iloc[0]
    
    # 原始內容 (含中文)
    raw_sentence = str(target['example'])
    # 清洗內容 (純英文，僅用於出題計算)
    clean_sentence = re.sub(r'[\(（].*?[\)）]', '', raw_sentence).strip()
    
    word = str(target['word'])
    
    # 使用清洗過的句子製作「挖空題目」
    blank_sentence = re.sub(re.escape(word), " ______ ", clean_sentence, flags=re.IGNORECASE)
    
    dist = pd.read_sql_query("""
        SELECT word FROM vocabs WHERE word != ? AND pos = ? ORDER BY RANDOM() LIMIT 3
    """, conn, params=(word, target['pos']))
    
    options = dist['word'].tolist() + [word]
    random.shuffle(options)
    conn.close()
    
    return {
        "id": int(target["id"]), 
        "sentence": blank_sentence, # 這是給測驗介面顯示的（純英文且挖空）
        "answer": word,
        "options": options, 
        "example": raw_sentence,   # 【關鍵】這裡改回傳原始內容（含中文），用於解析
        "word": word,
        "point": target["point"]
    }

# ==============================================================================
# 語音發音優化（穩定版 + 快取概念）
# ==============================================================================
@st.cache_data(show_spinner=False)
def get_tts_base64(text):
    """將語音轉為 Base64 並快取，解決 200 Unknown 與 Lag 問題"""
    if not text: return None
    try:
        # 只取英文部分發音
        english_only = " ".join(re.findall(r'[a-zA-Z0-9\s\.,\?!\'\";:-]+', text))
        if not english_only.strip(): return None
        tts = gTTS(text=english_only, lang='en')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        return base64.b64encode(mp3_fp.getvalue()).decode()
    except:
        return None

def create_audio_button(text, button_text, theme_mode):
    audio_base64 = get_tts_base64(text)
    if audio_base64:
        bg_color = "#262730" if theme_mode == "深色" else "#F0F2F6"
        text_color = "white" if theme_mode == "深色" else "#31333F"
        html_code = f"""
        <audio id="audio_{hash(text)}" src="data:audio/mp3;base64,{audio_base64}"></audio>
        <button onclick="document.getElementById('audio_{hash(text)}').play()"
        style="width:100%;padding:10px;border-radius:10px;cursor:pointer;
        background:{bg_color};color:{text_color};border:1px solid #444;">
        {button_text}
        </button>
        """
        components.html(html_code, height=55)
    else:
        st.write("🚫 無語音")

# ------------------------------------------------------------------------------
# 🧠 FSRS-like memory score (simple version)
# ------------------------------------------------------------------------------
def calculate_memory_strength(wrong_count, correct_streak):
    """
    模擬記憶強度（越高越記得）
    """
    return max(0.1, correct_streak * 2 - wrong_count * 1.5)


# ------------------------------------------------------------------------------
# 🔁 取得「快忘記的單字」
# ------------------------------------------------------------------------------
def get_review_words(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
        SELECT v.*, 
               IFNULL(p.wrong_count,0) as wrongs,
               IFNULL(p.correct_streak,0) as streak
        FROM vocabs v
        LEFT JOIN user_progress p
        ON v.id = p.vocab_id AND p.user_id = ?
    """, conn, params=(user_id,))

    conn.close()

    if df.empty:
        return []

    df["memory_score"] = df.apply(
        lambda x: calculate_memory_strength(x["wrongs"], x["streak"]),
        axis=1
    )

    # 越低 = 越容易忘
    df = df.sort_values("memory_score").head(10)

    return df.to_dict("records")


# ------------------------------------------------------------------------------
# 🧩 Recall 測驗（不用選項，直接回想）
# ------------------------------------------------------------------------------
def get_recall_question(user_id):
    words = get_review_words(user_id)

    if not words:
        return None

    target = random.choice(words)

    return {
        "id": target["id"],
        "type": "recall",
        "definition": target["definition"],
        "answer": target["word"],
        "example": target["example"],
        "point": target["point"]
    }

def update_fsrs(user_id, vocab_id, rating):
    """
    rating:
    0 = 錯
    1 = 困難
    2 = 普通
    3 = 簡單
    """

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    row = c.execute("""
        SELECT interval, ease FROM user_progress
        WHERE user_id=? AND vocab_id=?
    """, (user_id, vocab_id)).fetchone()

    if row:
        interval, ease = row
    else:
        interval, ease = 1, 2.5

    # === FSRS-lite 更新規則 ===
    if rating == 0:  # 錯
        interval = 1
        ease = max(1.3, ease - 0.2)

    elif rating == 1:  # 困難
        interval = max(1, int(interval * 1.2))
        ease = max(1.3, ease - 0.1)

    elif rating == 2:  # 普通
        interval = int(interval * ease)

    elif rating == 3:  # 簡單
        interval = int(interval * ease * 1.3)
        ease += 0.05

    next_review = datetime.datetime.now() + datetime.timedelta(days=interval)

    c.execute("""
        INSERT INTO user_progress (user_id, vocab_id, interval, ease, next_review)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, vocab_id)
        DO UPDATE SET
            interval=?,
            ease=?,
            next_review=?
    """, (user_id, vocab_id, interval, ease, next_review,
          interval, ease, next_review))

    conn.commit()
    conn.close()

def get_due_words(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
        SELECT v.*, p.next_review
        FROM vocabs v
        JOIN user_progress p ON v.id = p.vocab_id
        WHERE p.user_id = ?
    """, conn, params=(user_id,))

    conn.close()

    if df.empty:
        return []

    now = datetime.datetime.now()

    df["next_review"] = pd.to_datetime(df["next_review"], errors="coerce")

    due = df[
        (df["next_review"].isna()) | (df["next_review"] <= now)
    ]

    return due.to_dict("records")
# ==============================================================================
# Sidebar
# ==============================================================================
st.sidebar.title("設定")
user_id = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("模式", ["測驗","🧠 記憶強化","🔁 需加強複習","🔁 今日複習", "學習進度分析", "新增單字庫"]) # 新增分析選項
old_practice_mode = st.session_state.get("last_practice_mode")
practice_mode = st.sidebar.selectbox("練習模式", ["單字", "填空", "錯題"])
if old_practice_mode != practice_mode:
    st.session_state.q = None
    st.session_state.state = "q"
    st.session_state.last_practice_mode = practice_mode
theme_mode = st.sidebar.radio("主題", ["深色","淺色"])

if st.sidebar.button("同步單字"):
    sync_data()
    st.sidebar.success("完成")

init_session()

# ==============================================================================
# CSS
# ==============================================================================
st.markdown("""
<style>
.card { background:#111827; padding:25px; border-radius:20px; text-align:center; margin-bottom:20px; }
.big { font-size:24px; color:white; }
.note-box { 
    line-height: 1.8; font-size: 16px; background: #1e1e1e; 
    padding: 15px; border-radius: 10px; border-left: 5px solid #00C853; 
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 主流程：測驗
# ==============================================================================
if mode == "測驗":
    if not user_id:
        st.warning("請輸入User ID")
        st.stop()

    TOTAL = 10
    if st.session_state.q is None:
        if practice_mode == "填空":
            st.session_state.q = get_cloze_question(user_id)
        else:
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q
    if q is None:
        st.warning("目前沒有題目")
        st.stop()

    st.progress(min(st.session_state.get("count", 1) / TOTAL, 1.0))
    st.markdown(f"🏆 {st.session_state.score}　🔥 {st.session_state.streak}")

    display_text = q.get("sentence", q.get("definition", ""))
    st.markdown(f'<div class="card"><div class="big">{display_text}</div></div>', unsafe_allow_html=True)

    if st.session_state.state == "q":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True):
                st.session_state.selected = opt
                st.session_state.state = "result"
                
                # --- 更新資料庫進度 ---
                conn = sqlite3.connect(DB_NAME)
                correct = q.get("answer") or q.get("correct")
                is_correct = opt == correct
                if is_correct:
                    conn.execute("""
                        INSERT INTO user_progress (user_id, vocab_id, correct_streak, last_tested)
                        VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id, vocab_id) DO UPDATE SET
                        correct_streak = correct_streak + 1, last_tested = CURRENT_TIMESTAMP
                    """, (user_id, q['id']))
                else:
                    conn.execute("""
                        INSERT INTO user_progress (user_id, vocab_id, wrong_count, correct_streak, last_tested)
                        VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id, vocab_id) DO UPDATE SET
                        wrong_count = wrong_count + 1, correct_streak = 0, last_tested = CURRENT_TIMESTAMP
                    """, (user_id, q['id']))
                conn.commit()
                conn.close()
                st.rerun()
    else:
        correct = q.get("answer") or q.get("correct")
        selected = st.session_state.selected
        is_correct = selected == correct

        if is_correct:
            st.success("✅ Correct")
            st.session_state.score += 10
            st.session_state.streak += 1
        else:
            st.error(f"❌ {correct}")
            st.session_state.wrong_list.append(q)

        st.markdown("### 📌 解析")
        ex_text = str(q.get("example") or "").replace("\n", "<br>")
        pt_text = str(q.get("point") or "").replace("\n", "<br>")
        
        if ex_text:
            st.markdown(f'<div class="note-box"><b>例句：</b><br>{ex_text}</div>', unsafe_allow_html=True)
        if pt_text:
            st.markdown(f'<div class="note-box" style="margin-top:10px; border-left-color: #FFA000;"><b>重點考點：</b><br>{pt_text}</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            create_audio_button(q.get("word",""), "🔊 單字", theme_mode)
        with col2:
            create_audio_button(q.get("example",""), "📢 例句", theme_mode)

        if st.button("下一題", use_container_width=True):
            st.session_state.q = None
            st.session_state.state = "q"
            st.session_state.count += 1
            st.rerun()

# ==============================================================================
# 主流程：學習進度分析（新增整合內容）
# ==============================================================================
elif mode == "學習進度分析":
    st.subheader("📊 我的學習戰報")
    conn = sqlite3.connect(DB_NAME)
    query = """
        SELECT v.word, v.definition, p.wrong_count, p.correct_streak, p.last_tested
        FROM user_progress p JOIN vocabs v ON p.vocab_id = v.id WHERE p.user_id = ?
        ORDER BY p.wrong_count DESC
    """
    df_progress = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()

    if df_progress.empty:
        st.info("💡 目前還沒有測驗紀錄，快去挑戰看看吧！")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("📖 已練習單字", len(df_progress))
        c2.metric("👑 精通單字", len(df_progress[df_progress['correct_streak'] >= 3]))
        c3.metric("💥 累計錯誤", int(df_progress['wrong_count'].sum()))

        st.write("### 😈 你的十大魔王單字")
        top_10 = df_progress[df_progress['wrong_count'] > 0].nlargest(10, 'wrong_count')
        if top_10.empty:
            st.success("🎉 目前沒有魔王單字！")
        else:
            try:
                fig = px.bar(top_10, x='wrong_count', y='word', orientation='h', 
                             color='wrong_count', color_continuous_scale='Reds', text_auto=True)
                fig.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False, height=350, margin=dict(l=0,r=20,t=10,b=10))
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"圖表渲染失敗: {e}")

        with st.expander("📂 詳細清單"):
            st.dataframe(df_progress, column_config={
                "word": "單字", "wrong_count": "錯誤 ❌",
                "correct_streak": st.column_config.ProgressColumn("熟練度", min_value=0, max_value=3)
            }, hide_index=True, use_container_width=True)

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
            requests.post(url, json={"word": w, "definition": d, "example": ex, "point": pt})
            st.success("完成")
# ==============================================================================
# 🧠 新增 MODE：學習科學入口
# ==============================================================================
elif mode == "🧠 記憶強化":

    st.title("🧠 記憶強化模式（Learning Science Mode）")

    if not user_id:
        st.warning("請輸入 User ID")
        st.stop()

    # =========================
    # 初始化 state
    # =========================
    if "recall_state" not in st.session_state:
        st.session_state.recall_state = "question"

    if "recall_q" not in st.session_state or st.session_state.recall_q is None:
        st.session_state.recall_q = get_recall_question(user_id)

    q = st.session_state.recall_q

    if q is None:
        st.info("目前沒有需要複習的單字 🎉")
        st.stop()

    # =========================
    # 顯示題目
    # =========================
    st.markdown(f"""
    <div class="card">
        <div class="big">💡 {q['definition']}</div>
    </div>
    """, unsafe_allow_html=True)

    # =========================
    # 作答階段
    # =========================
    if st.session_state.recall_state == "question":

        user_input = st.text_input("請輸入英文單字（Recall）", key="recall_input")

        if st.button("提交"):

            correct = user_input.strip().lower() == q["answer"].lower()

            conn = sqlite3.connect(DB_NAME)

            if correct:
                st.session_state.recall_result = "🎉 正確！記憶加深"
                conn.execute("""
                    INSERT INTO user_progress (user_id, vocab_id, correct_streak, last_tested)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, vocab_id)
                    DO UPDATE SET correct_streak = correct_streak + 2
                """, (user_id, q["id"]))
            else:
                st.session_state.recall_result = f"❌ 錯誤，正確答案：{q['answer']}"
                conn.execute("""
                    INSERT INTO user_progress (user_id, vocab_id, wrong_count, correct_streak, last_tested)
                    VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, vocab_id)
                    DO UPDATE SET wrong_count = wrong_count + 2, correct_streak = 0
                """, (user_id, q["id"]))

            conn.commit()
            conn.close()

            # 👉 只切狀態，不 rerun 換題
            st.session_state.recall_state = "result"

    # =========================
    # 結果階段（重點）
    # =========================
    if st.session_state.recall_state == "result":

        # 顯示對錯結果（固定存在）
        st.markdown(f"## {st.session_state.recall_result}")

        st.markdown("### 📌 例句")
        st.write(q.get("example", ""))

        st.markdown("### 🎯 考點")
        st.write(q.get("point", ""))

        # 下一題才換
        if st.button("下一題 ➜"):

            st.session_state.recall_q = get_recall_question(user_id)
            st.session_state.recall_state = "question"

            # 清掉輸入狀態
            if "recall_input" in st.session_state:
                st.session_state.recall_input = ""

            st.rerun()

# ==============================================================================
# 🔁 今日複習 Dashboard
# ==============================================================================

elif mode == "🔁 今日複習":

    st.title("🔁 今日複習清單")

    if not user_id:
        st.warning("請輸入 User ID")
        st.stop()

    words = get_review_words(user_id)

    if not words:
        st.success("目前沒有需要複習的單字 🎉")
        st.stop()

    for w in words:

        st.markdown(f"""
        <div class="card">
            <div class="big">{w['word']}</div>
            <p>{w['definition']}</p>
        </div>
        """, unsafe_allow_html=True)

        st.progress(min(w.get("correct_streak", 0) / 5, 1.0))

elif mode == "🔁 需加強複習":

    st.title("🔁 FSRS 智慧複習")

    if not user_id:
        st.warning("請輸入 User ID")
        st.stop()

    if "fsrs_q" not in st.session_state:
        words = get_due_words(user_id)
        if words:
            st.session_state.fsrs_q = random.choice(words)
        else:
            st.session_state.fsrs_q = None

    q = st.session_state.fsrs_q

    if q is None:
        st.success("🎉 今天沒有需要複習的單字！")
        st.stop()

    st.markdown(f"""
    <div class="card">
        <div class="big">{q['word']}</div>
        <p>{q['definition']}</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🤔 你記得嗎？")

    col1, col2, col3, col4 = st.columns(4)

    if col1.button("❌ 忘記"):
        update_fsrs(user_id, q["id"], 0)
        st.session_state.fsrs_q = None
        st.rerun()

    if col2.button("😵 困難"):
        update_fsrs(user_id, q["id"], 1)
        st.session_state.fsrs_q = None
        st.rerun()

    if col3.button("🙂 普通"):
        update_fsrs(user_id, q["id"], 2)
        st.session_state.fsrs_q = None
        st.rerun()

    if col4.button("😎 簡單"):
        update_fsrs(user_id, q["id"], 3)
        st.session_state.fsrs_q = None
        st.rerun()
