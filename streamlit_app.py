import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime

# ==============================================================================
# 第一部分：【頁面與主題設定】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 優先獲取主題模式
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    st.write("---")

# 設定動態顏色
if theme_mode == "深色模式 (Dark)":
    main_bg, card_bg, text_color, sub_text, label_bg, card_shadow = "#0E1117", "#1E1E1E", "#FFFFFF", "#888888", "#333333", "rgba(0,0,0,0.5)"
else:
    main_bg, card_bg, text_color, sub_text, label_bg, card_shadow = "#FFFFFF", "#F0F2F6", "#1F1F1F", "#555555", "#E0E0E0", "rgba(0,0,0,0.1)"

st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg} !important; color: {text_color} !important; }}
    [data-testid="stSidebar"] {{ background-color: {main_bg} !important; }}
    .stButton>button {{ border-radius: 10px; font-weight: bold; height: 3.5em; border: 1px solid #444; background-color: {card_bg} !important; color: {text_color} !important; }}
    .stButton>button:hover {{ border-color: #FF4B4B !important; color: #FF4B4B !important; }}
    </style>
""", unsafe_allow_html=True)

st.title("📖 多益 (TOEIC) 單字強化戰情室")

# ==============================================================================
# 第二部分：【資料連線與安全檢查】
# ==============================================================================
# 確保 df 永遠存在
df = pd.DataFrame()

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="1m")
except Exception as e:
    st.error("Google Sheets 連線失敗")
    df = pd.DataFrame() # 確保出錯時 df 是一個空的 DataFrame 而不是 None

# 在呼叫時，確保傳入 df
if st.session_state.get('quiz_data') is None and not df.empty:
    generate_question(df)

# ==============================================================================
# 第三部分：【核心邏輯】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

def generate_question(data_df):
    # 第一道防線：檢查 data_df 是否為 None 或不是 DataFrame
    if data_df is None or not isinstance(data_df, pd.DataFrame):
        return
    
    # 第二道防線：檢查是否為空
    if data_df.empty:
        return

    try:
        target = data_df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        # 確保資料量足夠生成干擾項
        if len(data_df) >= 4:
            distractors = data_df[data_df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
        else:
            distractors = ["選項A", "選項B", "選項C"]
            
        options = distractors + [correct_ans]
        random.shuffle(options)
        
        st.session_state.quiz_data = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options
        }
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"題目生成時發生邏輯錯誤: {e}")

# 初始生成題目
if st.session_state.quiz_data is None and not df.empty:
    generate_question()

# ==============================================================================
# 第四部分：【UI 畫面】
# ==============================================================================
with st.sidebar:
    st.header("📊 學習狀態")
    c1, c2 = st.columns(2)
    c1.metric("正確數", st.session_state.score)
    c2.metric("總題數", st.session_state.total_answered)
    st.write("---")
    mode = st.radio("🚀 選擇功能模式", ["開始測驗", "新增單字庫", "錯題複習"])
    if st.button("♻️ 重置所有進度", use_container_width=True):
        st.session_state.update({"score": 0, "total_answered": 0, "wrong_answers": [], "quiz_data": None})
        st.rerun()

if mode == "開始測驗":
    if df.empty:
        st.warning("📭 請先到『新增單字庫』模式加入單字。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        st.markdown(f"""
            <div style="background-color: {card_bg}; padding: 35px; border-radius: 20px; border: 1px solid #444; border-left: 10px solid #FF4B4B; margin-bottom: 25px; box-shadow: 0 10px 20px {card_shadow}; text-align: center;">
                <p style="color: {sub_text}; margin-bottom: 10px; font-size: 1.1em; letter-spacing: 2px;">VOCABULARY QUIZ</p>
                <h2 style="color: {text_color} !important; margin: 15px 0; font-size: 2.2em;">請選出「 <span style="color: #FF4B4B; font-weight: 900;">{q['word']}</span> 」的正確定義</h2>
                <div style="margin-top: 20px;"><span style="background-color: {label_bg}; padding: 6px 18px; border-radius: 25px; font-size: 0.9em; color: #FF4B4B; border: 1px solid #444; font-weight: bold;">PART OF SPEECH: {q['pos']}</span></div>
            </div>
        """, unsafe_allow_html=True)

        cols = st.columns(2)
        for i, option in enumerate(q['options']):
            with cols[i % 2]:
                if st.button(option, use_container_width=True, key=f"btn_{i}"):
                    if not st.session_state.ans_revealed:
                        st.session_state.total_answered += 1
                        if option == q['correct_ans']:
                            st.session_state.score += 1
                            st.session_state.is_correct = True
                            st.balloons()
                        else:
                            st.session_state.is_correct = False
                            st.session_state.wrong_answers.append({"單字": q['word'], "詞性": q['pos'], "正確定義": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")})
                        st.session_state.ans_revealed = True

        if st.session_state.ans_revealed:
            st.write("---")
            if st.session_state.is_correct: st.success(f"🎊 **回答正確！**")
            else: st.error(f"⚠️ **回答錯誤！** 正確答案：**{q['correct_ans']}**")
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question()
                st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 擴充資料庫")
    SCRIPT_URL = st.secrets["connections"]["gsheets"]["script_url"]
    with st.form("add_form", clear_on_submit=True):
        w = st.text_input("英文單字"); p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."]); d = st.text_input("中文定義")
        if st.form_submit_button("💾 儲存"):
            if w and d:
                res = requests.post(SCRIPT_URL, json={"method": "write", "word": w, "pos": p, "definition": d})
                if res.status_code == 200:
                    st.success("成功！"); st.cache_data.clear()
            else: st.warning("請填寫內容。")

elif mode == "錯題複習":
    st.subheader("🔍 我的錯題本")
    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
        if st.button("🗑️ 清空記錄", use_container_width=True):
            st.session_state.wrong_answers = []; st.rerun()
    else: st.info("目前沒有錯題記錄！")
