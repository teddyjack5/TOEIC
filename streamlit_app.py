import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
import json

# ==============================================================================
# 第一部分：【頁面設定與美化樣式】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="🎓", layout="centered")

# 注入美編高手的自定義 CSS
st.markdown("""
    <style>
    /* 全域背景微調 */
    .stApp { background-color: #0E1117; }
    
    /* 單字大標題：霓虹藍光效果 */
    .word-header {
        font-size: 3.8rem !important;
        font-weight: 800 !important;
        color: #00D4FF;
        text-shadow: 0px 0px 15px rgba(0,212,255,0.6);
        margin-top: 20px;
        margin-bottom: 5px;
        text-align: center;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* 詞性標籤 */
    .pos-tag {
        background-color: #262730;
        color: #A0A4B8;
        padding: 4px 15px;
        border-radius: 20px;
        font-size: 1.1rem;
        display: inline-block;
        margin-bottom: 30px;
        border: 1px solid #3e4249;
    }

    /* 選項按鈕優化 */
    div.stButton > button {
        width: 100%;
        border-radius: 15px;
        height: 3.8rem;
        background-color: #1E2028;
        border: 1px solid #3e4249;
        color: #E0E0E0;
        font-size: 1.2rem;
        font-weight: 500;
        transition: all 0.3s ease;
        margin-bottom: 10px;
    }
    
    /* 滑鼠懸停效果：變亮並輕微浮起 */
    div.stButton > button:hover {
        border-color: #00D4FF;
        color: #00D4FF;
        background-color: #262730;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(0,212,255,0.2);
    }
    
    /* 下一題按鈕特殊色 */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(45deg, #00D4FF, #0072FF);
        border: none;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 第二部分：【資料連線與寫入邏輯】
# ==============================================================================
# 取得 Secrets 中的設定
try:
    SCRIPT_URL = st.secrets["connections"]["gsheets"]["script_url"]
except:
    st.error("❌ 找不到 script_url，請檢查 Secrets 設定")
    st.stop()

def upload_new_word(word, pos, definition, example):
    """沿用股市 App 的 GAS 寫入方式"""
    payload = {"word": word, "pos": pos, "definition": definition, "example": example}
    try:
        response = requests.post(
            SCRIPT_URL, 
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        return response.text == "Success"
    except:
        return False

# 建立 Google Sheets 連線 (讀取模式)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="5m")
except Exception as e:
    st.error("⚠️ 無法連線至雲端資料庫，請檢查連線設定")
    st.stop()

# ==============================================================================
# 第三部分：【測驗核心邏輯】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False

def get_new_question():
    if df is None or df.empty:
        st.stop()
    
    # 抽樣邏輯 (加入保護機制)
    target = df.sample(1).iloc[0]
    remaining = df[df['word'] != target['word']]
    num_distractors = min(len(remaining), 3)
    
    distractors = remaining.sample(num_distractors)['definition'].tolist()
    options = distractors + [target['definition']]
    random.shuffle(options)
    
    st.session_state.quiz_data = {
        'word': target['word'], 'pos': target['pos'],
        'correct_ans': target['definition'], 'example': target['example'],
        'options': options
    }
    st.session_state.ans_revealed = False

if st.session_state.quiz_data is None:
    get_new_question()

q = st.session_state.quiz_data

# ==============================================================================
# 第四部分：【主介面 UI 排版】
# ==============================================================================
# 頂部裝飾
st.markdown(f'<p class="word-header">{q["word"]}</p>', unsafe_allow_html=True)
st.markdown(f'<div style="text-align:center;"><span class="pos-tag">{q["pos"]}</span></div>', unsafe_allow_html=True)

st.write("")
st.markdown("##### 🎯 請選擇正確的定義：")

# 選項按鈕佈局
for option in q['options']:
    if st.button(option, key=f"btn_{option}"):
        if not st.session_state.ans_revealed:
            st.session_state.total_answered += 1
            if option == q['correct_ans']:
                st.session_state.score += 1
                st.balloons()
                st.success("✨ 回答正確！")
            else:
                st.error(f"❌ 答錯了！正確答案是：{q['correct_ans']}")
            st.session_state.ans_revealed = True

# 解答與例句區
if st.session_state.ans_revealed:
    st.markdown("---")
    with st.expander("📖 查看詳細解說與例句", expanded=True):
        st.write(f"**【單字解釋】**：{q['correct_ans']}")
        st.info(f"📚 **例句 연습 (Example)：**\n\n{q['example']}")
    
    if st.button("下一題 Next ➡️", type="primary"):
        get_new_question()
        st.rerun()

# ==============================================================================
# 第五部分：【側邊欄：進度監控與單字新增】
# ==============================================================================
with st.sidebar:
    st.title("🎓 學習儀表板")
    
    # 顯示計分
    col_a, col_b = st.columns(2)
    col_a.metric("得分", st.session_state.score)
    col_b.metric("總題數", st.session_state.total_answered)
    
    acc = (st.session_state.score / st.session_state.total_answered * 100) if st.session_state.total_answered > 0 else 0
    st.write(f"當前正確率：{acc:.1f}%")
    st.progress(acc / 100)

    if st.button("♻️ 重置數據"):
        st.session_state.score = 0
        st.session_state.total_answered = 0
        st.rerun()

    st.markdown("---")
    st.subheader("➕ 快速新增單字")
    with st.form("add_word_form", clear_on_submit=True):
        new_w = st.text_input("英文單字")
        new_p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
        new_d = st.text_input("中文定義")
        new_e = st.text_area("例句練習")
        
        if st.form_submit_button("🚀 同步到雲端"):
            if new_w and new_d:
                if upload_new_word(new_w, new_p, new_d, new_e):
                    st.toast("✅ 已成功寫入 Google Sheets！")
                else:
                    st.error("寫入失敗，請確認 GAS 網址")
            else:
                st.warning("請填寫必填欄位")

    st.write("---")
    st.caption("小鐵的專業多益助手 v2.0")
