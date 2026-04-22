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

# 初始化所有 Session State (必須放在最前面)
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

# 設定主題顏色
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    st.write("---")

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
# 第二部分：【核心函式】
# ==============================================================================
def generate_question(data_df):
    """生成單字題目，增加嚴格的資料檢查"""
    # 強制檢查輸入資料是否合法
    if data_df is None or not isinstance(data_df, pd.DataFrame) or data_df.empty:
        return

    try:
        # 隨取一個單字
        target = data_df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        # 抽取干擾項
        if len(data_df) >= 4:
            distractors = data_df[data_df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
        else:
            distractors = ["資料不足-A", "資料不足-B", "資料不足-C"]
            
        options = distractors + [correct_ans]
        random.shuffle(options)
        
        # 存入 Session State
        st.session_state.quiz_data = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options
        }
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"題目抽樣失敗，請確認資料表欄位是否正確：{e}")

# ==============================================================================
# 第三部分：【資料讀取邏輯】
# ==============================================================================
df = pd.DataFrame() # 預設空表

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="1m")
except Exception as e:
    st.error(f"❌ 雲端資料庫連線失敗")
    df = pd.DataFrame()

# 檢查：如果 Session 裡沒題目，且資料表有資料，才生成
if st.session_state.quiz_data is None:
    if df is not None and not df.empty:
        generate_question(df)

# ==============================================================================
# 第四部分：【UI 邏輯】
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

# --- 模式 1：測驗模式 ---
if mode == "開始測驗":
    if df.empty:
        st.warning("📭 單字庫空空的... 請先到『新增單字庫』輸入資料。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        
        st.markdown(f"""
            <div style="background-color: {card_bg}; padding: 35px; border-radius: 20px; border-left: 10px solid #FF4B4B; text-align: center; box-shadow: 0 10px 20px {card_shadow};">
                <h2 style="color: {text_color} !important;">請選出「 <span style="color: #FF4B4B;">{q['word']}</span> 」的正確定義</h2>
                <span style="background-color: {label_bg}; padding: 5px 15px; border-radius: 15px; color: #FF4B4B; font-weight: bold;">詞性: {q['pos']}</span>
            </div>
        """, unsafe_allow_html=True)
        st.write("")

        cols = st.columns(2)
        for i, option in enumerate(q['options']):
            with cols[i % 2]:
                if st.button(option, use_container_width=True, key=f"ans_{i}"):
                    if not st.session_state.ans_revealed:
                        st.session_state.total_answered += 1
                        if option == q['correct_ans']:
                            st.session_state.score += 1
                            st.session_state.is_correct = True
                            st.balloons()
                        else:
                            st.session_state.is_correct = False
                            st.session_state.wrong_answers.append({
                                "單字": q['word'], "詞性": q['pos'], "正確定義": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")
                            })
                        st.session_state.ans_revealed = True

        if st.session_state.ans_revealed:
            st.write("---")
            if st.session_state.is_correct:
                st.success("🎉 太棒了！回答正確。")
            else:
                st.error(f"❌ 答錯了！正確答案是：{q['correct_ans']}")
            
            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question(df)
                st.rerun()

# --- 模式 2：新增單字 ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    try:
        url = st.secrets["connections"]["gsheets"]["script_url"]
        with st.form("add_word_form", clear_on_submit=True):
            w = st.text_input("英文單字 (Word)")
            p = st.selectbox("詞性 (POS)", ["n.", "v.", "adj.", "adv.", "phr."])
            d = st.text_input("中文定義 (Definition)")
            if st.form_submit_button("💾 儲存並同步"):
                if w and d:
                    res = requests.post(url, json={"method": "write", "word": w, "pos": p, "definition": d})
                    if res.status_code == 200:
                        st.success(f"✅ {w} 已成功寫入！")
                        st.cache_data.clear()
                    else: st.error("寫入失敗。")
                else: st.warning("請完整填寫欄位。")
    except:
        st.error("請確認 Secrets 中的 script_url 設定是否正確。")

# --- 模式 3：錯題本 ---
elif mode == "錯題複習":
    st.subheader("🔍 錯題記錄")
    if st.session_state.wrong_answers:
        st.dataframe(pd.DataFrame(st.session_state.wrong_answers), use_container_width=True)
        if st.button("🗑️ 刪除所有記錄"):
            st.session_state.wrong_answers = []
            st.rerun()
    else:
        st.info("目前表現完美，沒有錯題記錄！")
