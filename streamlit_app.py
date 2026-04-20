import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random

# ==============================================================================
# 第一部分：【頁面設定與資料連線】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖")

st.title("📖 多益 (TOEIC) 單字強化測驗")

# 建立 Google Sheets 連線 (需在 Secrets 設定憑證)
# 建議在 Secrets 中設定 spreadsheet 網址
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="10m") # 每 10 分鐘更新一次資料緩存
except Exception as e:
    st.error(f"無法連線至 Google Sheets，請檢查 Secrets 設定。錯誤: {e}")
    st.stop()

# ==============================================================================
# 第二部分：【測驗邏輯控制】
# ==============================================================================
# 初始化 Session State (確保切換題目時狀態不會跑掉)
if 'quiz_data' not in st.session_state:
    st.session_state.quiz_data = None
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'total_answered' not in st.session_state:
    st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state:
    st.session_state.ans_revealed = False

def get_new_question():
    """隨機抽取一個單字並生成選項"""
    target = df.sample(1).iloc[0]
    # 隨機抓取另外三個錯誤定義當作誘答項
    distractors = df[df['word'] != target['word']].sample(3)['definition'].tolist()
    options = distractors + [target['definition']]
    random.shuffle(options)
    
    st.session_state.quiz_data = {
        'word': target['word'],
        'pos': target['pos'],
        'correct_ans': target['definition'],
        'example': target['example'],
        'options': options
    }
    st.session_state.ans_revealed = False

# 如果沒有題目，就初始化第一題
if st.session_state.quiz_data is None:
    get_new_question()

# ==============================================================================
# 第三部分：【測驗介面 UI】
# ==============================================================================
q = st.session_state.quiz_data

# 側邊欄計分板
st.sidebar.header("📊 學習進度")
st.sidebar.metric("正確數", st.session_state.score)
st.sidebar.metric("總題數", st.session_state.total_answered)
if st.sidebar.button("♻️ 重置測驗"):
    st.session_state.score = 0
    st.session_state.total_answered = 0
    st.rerun()

# 主畫面測驗區
st.write("---")
st.subheader(f"請選出單字 **「 {q['word']} 」** 的正確定義：")
st.caption(f"詞性：{q['pos']}")

# 建立選擇題按鈕
for option in q['options']:
    if st.button(option, use_container_width=True):
        if not st.session_state.ans_revealed:
            st.session_state.total_answered += 1
            if option == q['correct_ans']:
                st.session_state.score += 1
                st.success("✅ 回答正確！")
            else:
                st.error(f"❌ 回答錯誤！正確答案是：{q['correct_ans']}")
            st.session_state.ans_revealed = True

# 顯示詳細解答
if st.session_state.ans_revealed:
    st.info(f"📚 **例句練習：**\n\n{q['example']}")
    if st.button("下一題 ➡️"):
        get_new_question()
        st.rerun()

# ==============================================================================
# 第四部分：【資料庫管理模式】 (選配)
# ==============================================================================
with st.expander("📝 檢視目前所有單字"):
    st.dataframe(df, use_container_width=True)