import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime

# ==============================================================================
# 第一部分：【頁面設定與動態主題】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 在側邊欄最上方設定主題，確保 CSS 能即時讀取
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    st.write("---")

# 定義顏色變數 (使用 !important 強制覆蓋 Edge 渲染)
if theme_mode == "深色模式 (Dark)":
    main_bg, card_bg, text_color, sub_text, label_bg = "#0E1117", "#1E1E1E", "#FFFFFF", "#888888", "#333333"
else:
    main_bg, card_bg, text_color, sub_text, label_bg = "#FFFFFF", "#F0F2F6", "#1F1F1F", "#555555", "#E0E0E0"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg} !important; color: {text_color} !important; }}
    [data-testid="stSidebar"] {{ background-color: {main_bg} !important; }}
    h2, p, span {{ color: {text_color}; }}
    .stButton>button {{ background-color: {card_bg} !important; color: {text_color} !important; border-radius: 10px; border: 1px solid #444; }}
    </style>
""", unsafe_allow_html=True)

st.title("📖 多益 (TOEIC) 單字強化戰情室")

# ==============================================================================
# 第二部分：【資料連線與防呆】
# ==============================================================================
# 初始化 df，防止 NoneType 錯誤
df = pd.DataFrame() 

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="1m") 
except Exception as e:
    st.error("⚠️ 無法連線至 Google Sheets，請檢查 Secrets 或網路連線。")

# ==============================================================================
# 第三部分：【測驗邏輯】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

def generate_question():
    # 這裡加入對全域變數 df 的安全檢查
    global df
    if df is None or df.empty:
        return

    target = df.sample(n=1).iloc[0]
    correct_ans = target['definition']
    distractors = df[df['definition'] != correct_ans].sample(n=min(3, len(df)-1))['definition'].tolist()
    
    options = distractors + [correct_ans]
    random.shuffle(options)
    st.session_state.quiz_data = {'word': target['word'], 'correct_ans': correct_ans, 'pos': target['pos'], 'options': options}
    st.session_state.ans_revealed = False
    st.session_state.is_correct = None

# 如果還沒有題目且資料準備好了，就生成一題
if st.session_state.quiz_data is None and not df.empty:
    generate_question()

# ==============================================================================
# 第四部分：【UI 模式切換】
# ==============================================================================
with st.sidebar:
    st.header("📊 學習狀態")
    c1, c2 = st.columns(2)
    c1.metric("正確數", st.session_state.score)
    c2.metric("總題數", st.session_state.total_answered)
    mode = st.radio("🚀 選擇功能模式", ["開始測驗", "新增單字庫", "錯題複習"])

# --- 模式：開始測驗 ---
if mode == "開始測驗":
    if df.empty:
        st.warning("📭 目前單字庫空空如也，請先前往『新增單字庫』。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        # 題目卡片
        st.markdown(f"""
            <div style="background-color: {card_bg}; padding: 40px; border-radius: 20px; border-left: 10px solid #FF4B4B; text-align: center; border: 1px solid #444;">
                <h2 style="color: {text_color};">請選出「 <span style="color: #FF4B4B; font-weight: 900;">{q['word']}</span> 」的正確定義</h2>
                <span style="background-color: {label_bg}; padding: 5px 15px; border-radius: 20px; color: #FF4B4B; font-weight: bold;">{q['pos']}</span>
            </div>
        """, unsafe_allow_html=True)

        st.write("")
        cols = st.columns(2)
        for i, option in enumerate(q['options']):
            with cols[i % 2]:
                if st.button(option, use_container_width=True, key=f"btn_{i}"):
                    if not st.session_state.ans_revealed:
                        st.session_state.total_answered += 1
                        if option == q['correct_ans']:
                            st.session_state.score += 1
                            st.session_state.is_correct = True
                        else:
                            st.session_state.is_correct = False
                            if not any(item['單字'] == q['word'] for item in st.session_state.wrong_answers):
                                st.session_state.wrong_answers.append({"單字": q['word'], "正確定義": q['correct_ans']})
                        st.session_state.ans_revealed = True

        if st.session_state.ans_revealed:
            if st.session_state.is_correct: st.success(f"✅ 正確！")
            else: st.error(f"❌ 錯誤！正確答案：{q['correct_ans']}")
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question()
                st.rerun()

# --- 模式：新增單字庫 (透過 Script URL) ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充資料庫")
    SCRIPT_URL = st.secrets["connections"]["gsheets"]["script_url"]
    with st.form("add_form", clear_on_submit=True):
        w = st.text_input("單字"); p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv."]); d = st.text_input("定義")
        if st.form_submit_button("💾 儲存"):
            if w and d:
                res = requests.post(SCRIPT_URL, json={"method": "write", "word": w, "pos": p, "definition": d})
                if res.status_code == 200:
                    st.success("成功！"); st.cache_data.clear()
            else: st.warning("請填寫完整")
