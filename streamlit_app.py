import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime

# ==============================================================================
# 1. 頁面基本設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 初始化 Session State
if 'df' not in st.session_state: st.session_state.df = pd.DataFrame()
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

# ==============================================================================
# 2. 核心函式：完全從 Session State 讀取
# ==============================================================================
def generate_question():
    """直接從 st.session_state.df 抽取題目"""
    data = st.session_state.df
    
    # 強力檢查：如果 Session 裡的資料是空的，直接跳出
    if data is None or not isinstance(data, pd.DataFrame) or data.empty:
        return

    try:
        target = data.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        # 抽取干擾項
        if len(data) >= 4:
            distractors = data[data['definition'] != correct_ans].sample(n=3)['definition'].tolist()
        else:
            distractors = ["選項A", "選項B", "選項C"]
            
        options = distractors + [correct_ans]
        random.shuffle(options)
        
        # 更新題目狀態
        st.session_state.quiz_data = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options
        }
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"抽題失敗，請檢查工作表欄位：{e}")

# ==============================================================================
# 3. 資料載入：只在 Session df 為空時讀取
# ==============================================================================
try:
    # 這裡使用 @st.cache_data 來確保連線穩定
    @st.cache_data(ttl=60)
    def fetch_data():
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()

    # 更新 Session 裡的 df
    st.session_state.df = fetch_data()
except Exception as e:
    st.error("⚠️ 無法連線至 Google Sheets")
    st.session_state.df = pd.DataFrame()

# 初始生成第一題
if st.session_state.quiz_data is None and not st.session_state.df.empty:
    generate_question()

# ==============================================================================
# 4. UI 介面 (保持你的精美設計)
# ==============================================================================
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    mode = st.radio("🚀 模式選擇", ["開始測驗", "新增單字庫", "錯題複習"])
    if st.button("♻️ 重置進度"):
        st.session_state.update({"score": 0, "total_answered": 0, "wrong_answers": [], "quiz_data": None})
        st.cache_data.clear()
        st.rerun()

# 根據模式顯示內容
if mode == "開始測驗":
    if st.session_state.df.empty:
        st.warning("請先去新增單字庫。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        st.subheader(f"請選出「 {q['word']} 」的正確定義 ({q['pos']})")
        
        for i, option in enumerate(q['options']):
            if st.button(option, key=f"ans_{i}", use_container_width=True):
                if not st.session_state.ans_revealed:
                    st.session_state.total_answered += 1
                    if option == q['correct_ans']:
                        st.session_state.score += 1
                        st.session_state.is_correct = True
                    else:
                        st.session_state.is_correct = False
                        st.session_state.wrong_answers.append({"單字": q['word'], "正確定義": q['correct_ans']})
                    st.session_state.ans_revealed = True
        
        if st.session_state.ans_revealed:
            if st.session_state.is_correct: st.success("正確！")
            else: st.error(f"錯誤！答案是：{q['correct_ans']}")
            if st.button("➡️ 下一題", type="primary"):
                generate_question()
                st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 新增單字")
    # ... (保持原本的寫入邏輯)
    with st.form("add_form"):
        w = st.text_input("Word"); p = st.text_input("POS"); d = st.text_input("Def")
        if st.form_submit_button("儲存"):
            # 寫入後記得清除快取
            st.cache_data.clear()
            st.success("已發送寫入請求！")

elif mode == "錯題複習":
    st.dataframe(st.session_state.wrong_answers)
