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
# APP CONFIG
# ==============================================================================
st.set_page_config(
    page_title="TOEIC Duolingo Style App",
    page_icon="🟢",
    layout="centered"
)

DB_NAME = "toeic_pro.db"

# ==============================================================================
# DB
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS vocabs(
        id INTEGER PRIMARY KEY,
        word TEXT UNIQUE,
        pos TEXT,
        definition TEXT,
        example TEXT,
        point TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_progress(
        user_id TEXT,
        vocab_id INTEGER,
        wrong_count INTEGER DEFAULT 0,
        correct_streak INTEGER DEFAULT 0,
        last_tested TIMESTAMP,
        PRIMARY KEY(user_id, vocab_id)
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# SYNC GOOGLE SHEET
# ==============================================================================
def sync_data():
    conn_gs = st.connection("gsheets", type=GSheetsConnection)
    df = conn_gs.read()

    conn = sqlite3.connect(DB_NAME)

    for _, r in df.iterrows():
        conn.execute("""
        INSERT OR REPLACE INTO vocabs(word,pos,definition,example,point)
        VALUES(?,?,?,?,?)
        """, (r["word"], r["pos"], r["definition"], r["example"], r["point"]))

    conn.commit()
    conn.close()

# ==============================================================================
# PROGRESS UPDATE
# ==============================================================================
def update_progress(user_id, vocab_id, correct):
    conn = sqlite3.connect(DB_NAME)

    if correct:
        conn.execute("""
        INSERT INTO user_progress VALUES(?,?,0,1,CURRENT_TIMESTAMP)
        ON CONFLICT(user_id,vocab_id)
        DO UPDATE SET correct_streak = correct_streak + 1
        """, (user_id, vocab_id))
    else:
        conn.execute("""
        INSERT INTO user_progress VALUES(?,?,1,0,CURRENT_TIMESTAMP)
        ON CONFLICT(user_id,vocab_id)
        DO UPDATE SET wrong_count = wrong_count + 1, correct_streak = 0
        """, (user_id, vocab_id))

    conn.commit()
    conn.close()

# ==============================================================================
# DUOLINGO MAP (關卡系統)
# ==============================================================================
def render_map(level):
    nodes = ""
    for i in range(1, 11):
        if i < level:
            color = "#22c55e"
            status = "✔"
        elif i == level:
            color = "#facc15"
            status = "🔥"
        else:
            color = "#374151"
            status = "🔒"

        nodes += f"""
        <div style="
            width:70px;height:70px;
            border-radius:50%;
            background:{color};
            display:flex;
            align-items:center;
            justify-content:center;
            margin:10px auto;
            color:white;
            font-weight:bold;
            box-shadow:0 0 10px {color};
            animation:pop 1s ease;
        ">
            {status}<br>{i}
        </div>
        """

    st.markdown(f"""
    <style>
    @keyframes pop {{
        0% {{ transform:scale(0.6); opacity:0; }}
        100% {{ transform:scale(1); opacity:1; }}
    }}
    </style>

    <div style="text-align:center">
        {nodes}
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# CLOZE
# ==============================================================================
def get_cloze_question(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
    SELECT v.*, IFNULL(p.wrong_count,0) wrongs
    FROM vocabs v
    LEFT JOIN user_progress p
    ON v.id=p.vocab_id AND p.user_id=?
    WHERE v.example IS NOT NULL
    """, conn, params=(user_id,))

    if df.empty:
        return None

    row = df.sample(1).iloc[0]

    sentence = row["example"]
    word = row["word"]

    blank = re.sub(word, "_____", sentence, flags=re.I)

    dist = pd.read_sql_query("""
    SELECT word FROM vocabs
    WHERE word != ? LIMIT 3
    """, conn, params=(word,))

    options = dist["word"].tolist() + [word]
    random.shuffle(options)

    return {
        "type": "cloze",
        "sentence": blank,
        "answer": word,
        "options": options,
        "word": word,
        "example": sentence,
        "point": row["point"],
        "id": row["id"]
    }

# ==============================================================================
# NORMAL QUESTION
# ==============================================================================
def get_question(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
    SELECT v.*, IFNULL(p.wrong_count,0) wrongs
    FROM vocabs v
    LEFT JOIN user_progress p
    ON v.id=p.vocab_id AND p.user_id=?
    """, conn, params=(user_id,))

    row = df.sample(1).iloc[0]

    dist = pd.read_sql_query("""
    SELECT word FROM vocabs
    WHERE word != ? LIMIT 3
    """, conn, params=(row["word"],))

    options = dist["word"].tolist() + [row["word"]]
    random.shuffle(options)

    return {
        "type": "mcq",
        "definition": row["definition"],
        "answer": row["word"],
        "options": options,
        "word": row["word"],
        "example": row["example"],
        "point": row["point"],
        "id": row["id"]
    }

# ==============================================================================
# AUDIO
# ==============================================================================
def audio(text):
    if not text:
        return

    text = re.sub(r"[^a-zA-Z ]", "", text)

    tts = gTTS(text=text, lang="en")
    fp = io.BytesIO()
    tts.write_to_fp(fp)

    b64 = base64.b64encode(fp.getvalue()).decode()

    components.html(f"""
    <audio controls autoplay>
        <source src="data:audio/mp3;base64,{b64}">
    </audio>
    """, height=80)

# ==============================================================================
# UI STYLE
# ==============================================================================
st.markdown("""
<style>
.card{
    background:#111827;
    padding:25px;
    border-radius:20px;
    text-align:center;
    color:white;
    animation:fade 0.4s ease;
}

@keyframes fade{
    from{opacity:0; transform:translateY(10px);}
    to{opacity:1;}
}

button{
    border-radius:12px !important;
    height:60px !important;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR
# ==============================================================================
user = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("Mode", ["測驗","地圖"])
practice = st.sidebar.selectbox("Type", ["單字","填空"])

if st.sidebar.button("Sync"):
    sync_data()

# ==============================================================================
# SESSION
# ==============================================================================
if "q" not in st.session_state:
    st.session_state.q = None
    st.session_state.level = 1
    st.session_state.state = "q"
    st.session_state.score = 0

# ==============================================================================
# MAP MODE
# ==============================================================================
if mode == "地圖":
    st.title("🗺 Duolingo Map")
    render_map(st.session_state.level)
    st.stop()

# ==============================================================================
# QUESTION
# ==============================================================================
if st.session_state.q is None:
    if practice == "填空":
        st.session_state.q = get_cloze_question(user)
    else:
        st.session_state.q = get_question(user)

q = st.session_state.q

# ==============================================================================
# CARD
# ==============================================================================
if q["type"] == "cloze":
    text = q["sentence"]
else:
    text = q["definition"]

st.markdown(f"""
<div class="card">
    {text}
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# ANSWER
# ==============================================================================
if st.session_state.state == "q":

    for o in q["options"]:
        if st.button(o):
            st.session_state.selected = o
            st.session_state.state = "r"
            st.rerun()

else:
    ans = q["answer"]
    sel = st.session_state.selected

    correct = ans == sel

    update_progress(user, q["id"], correct)

    if correct:
        st.success("✔ Correct")
        st.session_state.score += 10
        st.session_state.level += 1
    else:
        st.error(f"❌ {ans}")

    st.markdown("### 📌 Explanation")
    st.info(q["point"])

    st.markdown("### 🔊")
    audio(q["word"])

    if st.button("Next"):
        st.session_state.q = None
        st.session_state.state = "q"
        st.rerun()
# ==============================================================================
# 新增單字（PRO UX VERSION）
# ==============================================================================
elif mode == "新增單字庫":
    st.subheader("➕ 新增單字（Pro Mode）")

    url = st.secrets["connections"]["gsheets"].get("script_url")

    # =========================
    # FORM
    # =========================
    with st.form("add_word"):
        w = st.text_input("英文單字")
        d = st.text_input("中文定義")
        ex = st.text_area("例句")
        pt = st.text_area("考點")

        submitted = st.form_submit_button("🚀 加入學習系統")

    # =========================
    # VALIDATION
    # =========================
    if submitted:

        if not w or not d:
            st.error("❌ 單字與定義不能為空")
            st.stop()

        # =========================
        # INSERT GOOGLE SHEET
        # =========================
        try:
            payload = {
                "word": w.strip(),
                "definition": d.strip(),
                "example": ex.strip(),
                "point": pt.strip()
            }

            res = requests.post(url, json=payload)

            # =========================
            # INSERT SQLITE（即時同步）
            # =========================
            conn = sqlite3.connect(DB_NAME)
            conn.execute("""
                INSERT OR REPLACE INTO vocabs(word,pos,definition,example,point)
                VALUES(?,?,?,?,?)
            """, (w, "n.", d, ex, pt))
            conn.commit()
            conn.close()

            # =========================
            # SUCCESS UI (APP LIKE)
            # =========================
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg,#22c55e,#16a34a);
                padding:25px;
                border-radius:20px;
                color:white;
                text-align:center;
                animation: pop 0.4s ease;
            ">
                <h2>🎉 新增成功！</h2>
                <h3>{w}</h3>
                <p>{d}</p>
            </div>

            <style>
            @keyframes pop {{
                0% {{transform:scale(0.6); opacity:0;}}
                100% {{transform:scale(1); opacity:1;}}
            }}
            </style>
            """, unsafe_allow_html=True)

            st.success("已同步到學習系統")

        except Exception as e:
            st.error(f"❌ 新增失敗：{e}")

    # =========================
    # LIVE PREVIEW
    # =========================
    st.markdown("### 👀 即時預覽")

    if w:
        st.markdown(f"""
        <div style="
            background:#111827;
            padding:20px;
            border-radius:15px;
            color:white;
        ">
            <h3>{w}</h3>
            <p>{d}</p>
            <small>{ex}</small>
        </div>
        """, unsafe_allow_html=True)
