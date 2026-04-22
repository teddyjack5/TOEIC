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

# 強制先初始化 Session State，確保 Key 永遠存在
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

# ==============================================================================
# 2. 核心函式：傳入 df 作為參數 (不再依賴外部變數)
# ==============================================================================
def generate_question(source_df):
    """
    接收 source_df 作為參數，避免 Scope 錯誤
    """
    if source_df is None or not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return

    try:
        target = source_df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        if len(source_df) >= 4:
            distractors = source_df[source_df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
        else:
            distractors = ["選項 A", "選項 B", "選項 C"]
            
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
        st.error(f"抽題發生邏輯錯誤：{e}")

# ==============================================================================
# 3. 資料載入流程
# ==============================================================================
# 封裝讀取邏輯
@st.cache_data(ttl=60)
def get_data_from_gsheets():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()
    except Exception:
        return pd.DataFrame()

# 執行讀取
df = get_data_from_gsheets()

# 初始生成題目：【重點：一定要傳 df 進去】
if st.session_state.quiz_data is None and not df.empty:
    generate_question(df)

# ==============================================================================
# 4. UI 介面
# ==============================================================================
st.title("📖 多益單字戰情室")

with st.sidebar:
    st.header("📊 學習狀態")
    st.metric("正確率", f"{st.session_state.score}/{st.session_state.total_answered}")
    mode = st.radio("🚀 選擇功能", ["開始測驗", "新增單字庫", "錯題複習"])
    if st.button("♻️ 重置進度"):
        st.session_state.update({"quiz_data": None, "score": 0, "total_answered": 0, "wrong_answers": []})
        st.cache_data.clear()
        st.rerun()

if mode == "開始測驗":
    if df.empty:
        st.warning("📭 單字庫目前是空的，請確認連線或新增單字。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        st.info(f"請選出「 {q['word']} 」({q['pos']}) 的正確定義：")
        
        # 顯示按鈕
        for i, option in enumerate(q['options']):
            if st.button(option, key=f"btn_{i}", use_container_width=True, disabled=st.session_state.ans_revealed):
                st.session_state.total_answered += 1
                if option == q['correct_ans']:
                    st.session_state.score += 1
                    st.session_state.is_correct = True
                    st.balloons()
                else:
                    st.session_state.is_correct = False
                    st.session_state.wrong_answers.append({"單字": q['word'], "正確答案": q['correct_ans']})
                st.session_state.ans_revealed = True
                st.rerun()
        
        # 顯示結果
        if st.session_state.ans_revealed:
            if st.session_state.is_correct: st.success("正確！")
            else: st.error(f"錯誤！正確答案是：{q['correct_ans']}")
            
            # 【重點：下一題也要傳 df】
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question(df)
                st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 擴充資料庫")
    # 這裡請確保你的 secrets 有正確設定
    try:
        script_url = st.secrets["connections"]["gsheets"]["script_url"]
        with st.form("add_form", clear_on_submit=True):
            w = st.text_input("Word")
            p = st.text_input("POS (n./v./adj.)")
            d = st.text_input("Definition")
            if st.form_submit_button("儲存"):
                if w and d:
                    res = requests.post(script_url, json={"method": "write", "word": w, "pos": p, "definition": d})
                    st.success("已發送寫入請求！資料將在 1 分鐘後同步。")
                    st.cache_data.clear()
                else: st.warning("請填寫完整。")
    except:
        st.error("請確認 secrets 設定。")

elif mode == "錯題複習":
    st.subheader("🔍 錯題記錄")
    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
    else:
        st.info("目前沒有錯題！")
