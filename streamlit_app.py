import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime

# ==============================================================================
# 1. 頁面基本設定與快取定義
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 將快取函式放在全域，避免重複定義
@st.cache_data(ttl=60)
def fetch_data():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()
    except Exception:
        return pd.DataFrame()

# 初始化 Session State
state_keys = {
    'df': pd.DataFrame(),
    'quiz_data': None,
    'score': 0,
    'total_answered': 0,
    'ans_revealed': False,
    'is_correct': None,
    'wrong_answers': []
}
for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ==============================================================================
# 2. 核心函式
# ==============================================================================
def generate_question():
    """直接從 st.session_state.df 抽取題目"""
    data = st.session_state.df
    if data is None or data.empty:
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
        
        st.session_state.quiz_data = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options
        }
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"抽題失敗：{e}")

# ==============================================================================
# 3. 資料載入主流程
# ==============================================================================
# 取得最新資料
fresh_df = fetch_data()
if not fresh_df.empty:
    st.session_state.df = fresh_df

# 初始生成第一題
if st.session_state.quiz_data is None and not st.session_state.df.empty:
    generate_question()

# ==============================================================================
# 4. UI 介面
# ==============================================================================
with st.sidebar:
    st.header("📊 學習戰情室")
    # 顯示分數
    st.metric("目前得分", f"{st.session_state.score} / {st.session_state.total_answered}")
    
    mode = st.radio("🚀 模式選擇", ["開始測驗", "新增單字庫", "錯題複習"])
    
    if st.button("♻️ 重置進度"):
        st.session_state.update({"score": 0, "total_answered": 0, "wrong_answers": [], "quiz_data": None})
        st.cache_data.clear()
        st.rerun()

if mode == "開始測驗":
    if st.session_state.df.empty:
        st.warning("📭 請檢查 Google Sheets 是否有資料或 Secrets 設定是否正確。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        st.title(f"請選出「 {q['word']} 」的正確定義")
        st.caption(f"詞性：{q['pos']}")
        
        # 使用 Columns 排版選項
        cols = st.columns(2)
        for i, option in enumerate(q['options']):
            with cols[i % 2]:
                # 如果已經揭曉答案，禁用按鈕增加視覺引導
                if st.button(option, key=f"ans_{i}", use_container_width=True, disabled=st.session_state.ans_revealed):
                    st.session_state.total_answered += 1
                    if option == q['correct_ans']:
                        st.session_state.score += 1
                        st.session_state.is_correct = True
                        st.balloons()
                    else:
                        st.session_state.is_correct = False
                        st.session_state.wrong_answers.append({
                            "單字": q['word'], "詞性": q['pos'], "正確答案": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")
                        })
                    st.session_state.ans_revealed = True
                    st.rerun() # 點擊後立即重新渲染顯示回饋
        
        if st.session_state.ans_revealed:
            st.divider()
            if st.session_state.is_correct:
                st.success("🎉 回答正確！")
            else:
                st.error(f"⚠️ 答錯了，正確答案是：{q['correct_ans']}")
            
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question()
                st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 擴充資料庫")
    # 確保 Secrets 存在
    try:
        url = st.secrets["connections"]["gsheets"]["script_url"]
        with st.form("add_form", clear_on_submit=True):
            w = st.text_input("英文單字")
            p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
            d = st.text_input("中文定義")
            if st.form_submit_button("儲存"):
                if w and d:
                    res = requests.post(url, json={"method": "write", "word": w, "pos": p, "definition": d})
                    if res.status_code == 200:
                        st.success("✅ 寫入成功！資料將在 60 秒內同步。")
                        st.cache_data.clear()
                    else: st.error("連線到 Google Apps Script 失敗。")
                else: st.warning("請填寫所有欄位。")
    except KeyError:
        st.error("請在 .streamlit/secrets.toml 中設定 script_url")

elif mode == "錯題複習":
    st.subheader("🔍 錯題本")
    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
    else:
        st.info("目前沒有錯題記錄，表現優異！")
