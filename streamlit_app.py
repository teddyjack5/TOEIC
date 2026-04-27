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
# SYNC
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
# PROGRESS
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
# MAP
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
        ">
            {status}<br>{i}
        </div>
        """

    st.markdown(f"""
    <div style="text-align:center">
        {nodes}
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# QUESTIONS
# ==============================================================================
def get_question(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
    SELECT * FROM vocabs
    """, conn)

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

def get_cloze_question(user_id):
    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query("""
    SELECT * FROM vocabs
    WHERE example IS NOT NULL
    """, conn)

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
# STYLE
# ==============================================================================
st.markdown("""
<style>
.card{
    background:#111827;
    padding:25px;
    border-radius:20px;
    text-align:center;
    color:white;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR
# ==============================================================================
user = st.sidebar.text_input("User ID")
mode = st.sidebar.radio("Mode", ["測驗", "地圖", "新增單字庫"])
practice = st.sidebar.selectbox("Type", ["單字", "填空"])

if st.sidebar.button("Sync"):
    sync_data()

# ==============================================================================
# STATE INIT
# ==============================================================================
if "q" not in st.session_state:
    st.session_state.q = None
    st.session_state.state = "q"
    st.session_state.level = 1
    st.session_state.score = 0

# ==============================================================================
# ROUTER（🔥 修正核心）
# ==============================================================================
if mode == "地圖":

    st.title("🗺 Map")
    render_map(st.session_state.level)
    st.stop()

# ==============================================================================
# 測驗
# ==============================================================================
if mode == "測驗":

    if st.session_state.q is None:
        if practice == "填空":
            st.session_state.q = get_cloze_question(user)
        else:
            st.session_state.q = get_question(user)

    q = st.session_state.q

    text = q["sentence"] if q["type"] == "cloze" else q["definition"]

    st.markdown(f"<div class='card'>{text}</div>", unsafe_allow_html=True)

    if st.session_state.state == "q":

        for o in q["options"]:
            if st.button(o):
                st.session_state.selected = o
                st.session_state.state = "r"
                st.rerun()

    else:
        correct = q["answer"]
        sel = st.session_state.selected
        ok = correct == sel

        update_progress(user, q["id"], ok)

        if ok:
            st.success("✔ Correct")
            st.session_state.score += 10
            st.session_state.level += 1
        else:
            st.error(correct)

        st.info(q["point"])
        audio(q["word"])

        if st.button("Next"):
            st.session_state.q = None
            st.session_state.state = "q"
            st.rerun()

# ==============================================================================
# 新增單字（🔥 完整修正）
# ==============================================================================
elif mode == "新增單字庫":

    st.subheader("➕ 新增單字")

    url = st.secrets["connections"]["gsheets"].get("script_url")

    with st.form("add"):
        w = st.text_input("word")
        d = st.text_input("definition")
        ex = st.text_area("example")
        pt = st.text_area("point")

        submit = st.form_submit_button("送出")

    if submit:

        if not w or not d:
            st.error("word / definition 不能空")
            st.stop()

        conn = sqlite3.connect(DB_NAME)
        conn.execute("""
        INSERT OR REPLACE INTO vocabs(word,pos,definition,example,point)
        VALUES(?,?,?,?,?)
        """, (w, "n.", d, ex, pt))
        conn.commit()
        conn.close()

        st.success("新增成功 🎉")
