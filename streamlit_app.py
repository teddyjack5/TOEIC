import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from datetime import datetime

# ==============================================================================
# 第一部分：【頁面設定與資料連線】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖")

st.title("📖 多益 (TOEIC) 單字強化測驗")

# 建立 Google Sheets 連線
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="10m") 
except Exception as e:
    st.error(f"無法連線至 Google Sheets，請檢查 Secrets 設定。錯誤: {e}")
    st.stop()

# ==============================================================================
# 第二部分：【測驗邏輯控制】
# ==============================================================================
# 初始化 Session State
if 'quiz_data' not in st.session_state:
    st.session_state.quiz_data = None
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'total_answered' not in st.session_state:
    st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state:
    st.session_state.ans_revealed = False
# 【新增】錯題本初始化
if 'wrong_answers' not in st.session_state:
    st.session_state.wrong_answers = []

def generate_question():
    """從資料表中隨機抽取單字並生成干擾選項"""
    target = df.sample(n=1).iloc[0]
    word = target['word']
    correct_ans = target['definition']
    pos = target['pos']
    
    # 隨機抽取 3 個錯誤答案作為干擾項
    distractors = df[df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
    
    options = distractors + [correct_ans]
    random.shuffle(options)
    
    st.session_state.quiz_data = {
        'word': word,
        'correct_ans': correct_ans,
        'pos': pos,
        'options': options
    }
    st.session_state.ans_revealed = False

# 首次執行生成題目
if st.session_state.quiz_data is None:
    generate_question()

# ==============================================================================
# 第三部分：【測驗介面 UI】
# ==============================================================================
q = st.session_state.quiz_data

# 側邊欄計分板
st.sidebar.header("📊 學習進度")
st.sidebar.metric("正確數", st.session_state.score)
st.sidebar.metric("總題數", st.session_state.total_answered)

# 顯示錯題本統計
st.sidebar.write("---")
st.sidebar.subheader("📝 錯題本統計")
st.sidebar.write(f"目前累積：{len(st.session_state.wrong_answers)} 個單字")

if st.sidebar.button("♻️ 重置測驗"):
    st.session_state.score = 0
    st.session_state.total_answered = 0
    st.rerun()

# 主畫面測驗區
st.write("---")
st.subheader(f"請選出單字 **「 {q['word']} 」** 的正確定義：")
st.caption(f"詞性：{q['pos']}\n")

# 建立選擇題按鈕
for option in q['options'] :
    if st.button(option, use_container_width=True, key=option):
        if not st.session_state.ans_revealed:
            st.session_state.total_answered += 1
            if option == q['correct_ans']:
                st.session_state.score += 1
                st.success("✅ 回答正確！")
            else:
                st.error(f"❌ 回答錯誤！正確答案是：{q['correct_ans']}")
                
                # 【關鍵功能】記錄錯題邏輯
                new_error = {
                    "單字": q['word'],
                    "詞性": q['pos'],
                    "正確定義": q['correct_ans'],
                    "記錄時間": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                # 檢查是否已在錯題本中，避免重複記錄
                if not any(item['單字'] == q['word'] for item in st.session_state.wrong_answers):
                    st.session_state.wrong_answers.append(new_error)
            
            st.session_state.ans_revealed = True

# 下一題按鈕
if st.session_state.ans_revealed:
    if st.button("➡️ 下一題", type="primary"):
        generate_question()
        st.rerun()

# ==============================================================================
# 第四部分：【錯題一覽表功能】
# ==============================================================================
st.write("---")
with st.expander("🔍 查看我的錯題一覽表", expanded=False):
    if st.session_state.wrong_answers:
        st.write("以下是你答錯過的單字，建議加強記憶：")
        
        # 轉換成 DataFrame 格式顯示
        error_df = pd.DataFrame(st.session_state.wrong_answers)
        
        # 美化顯示表格
        st.dataframe(
            error_df[["單字", "詞性", "正確定義", "記錄時間"]],
            use_container_width=True,
            hide_index=True
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ 清空錯題"):
                st.session_state.wrong_answers = []
                st.rerun()
    else:
        st.info("太棒了！目前錯題本空空如也，繼續保持全對吧！💪")
