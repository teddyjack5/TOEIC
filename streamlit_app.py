import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from datetime import datetime

# ==============================================================================
# 第一部分：【頁面設定與資料連線】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="1m") 
except Exception as e:
    st.error(f"無法連線至 Google Sheets，請檢查 Secrets 設定。")
    df = pd.DataFrame()

# 先獲取主題模式，確保 CSS 能讀到變數
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    st.write("---")

# 設定動態顏色變數
if theme_mode == "深色模式 (Dark)":
    main_bg = "#0E1117"     # 全域背景
    card_bg = "#1E1E1E"     # 卡片背景
    text_color = "#FFFFFF"  # 主文字
    sub_text = "#888888"    # 副標題
    label_bg = "#333333"    # 標籤背景
    card_shadow = "rgba(0,0,0,0.5)"
else:
    main_bg = "#FFFFFF"     # 全域背景
    card_bg = "#F0F2F6"     # 卡片背景
    text_color = "#1F1F1F"  # 主文字
    sub_text = "#555555"    # 副標題
    label_bg = "#E0E0E0"    # 標籤背景
    card_shadow = "rgba(0,0,0,0.1)"

# 強制渲染 CSS
st.markdown(f"""
    <style>
    /* 強制修改整體的背景與文字顏色，使用 !important 避免 Edge 干預 */
    .stApp {{
        background-color: {main_bg} !important;
        color: {text_color} !important;
    }}
    
    /* 側邊欄文字也一併修正 */
    [data-testid="stSidebar"] {{
        background-color: {main_bg} !important;
        border-right: 1px solid #333;
    }}

    .stButton>button {{
        border-radius: 10px;
        font-weight: bold;
        height: 3.5em;
        border: 1px solid #444;
        background-color: {card_bg} !important;
        color: {text_color} !important;
    }}
    
    .stButton>button:hover {{
        border-color: #FF4B4B !important;
        color: #FF4B4B !important;
    }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 第二部分：【核心邏輯與狀態管理】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None # 紀錄當前這題是否答對
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

def generate_question():
    if df.empty: return
    target = df.sample(n=1).iloc[0]
    correct_ans = target['definition']
    distractors = df[df['definition'] != correct_ans].sample(n=3)['definition'].tolist() if len(df) >= 4 else ["選項A", "選項B", "選項C"]
    options = distractors + [correct_ans]
    random.shuffle(options)
    st.session_state.quiz_data = {'word': target['word'], 'correct_ans': correct_ans, 'pos': target['pos'], 'options': options}
    st.session_state.ans_revealed = False
    st.session_state.is_correct = None

if st.session_state.quiz_data is None: generate_question()

# ==============================================================================
# 第三部分：【側邊欄】
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

with st.sidebar:
    st.header("🎨 介面設定")
    # 讓使用者手動選擇主題
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    st.write("---")
# ==============================================================================
# 第四部分：【主畫面 UI】
# ==============================================================================
if theme_mode == "深色模式 (Dark)":
    bg_color = "#1E1E1E"
    text_color = "#FFFFFF"
    sub_text = "#888888"
    card_shadow = "rgba(0,0,0,0.5)"
    label_bg = "#333333"
else:
    bg_color = "#F0F2F6"
    text_color = "#1F1F1F"
    sub_text = "#555555"
    card_shadow = "rgba(0,0,0,0.1)"
    label_bg = "#E0E0E0"

# 更新主卡片 UI
if mode == "開始測驗":
    q = st.session_state.quiz_data
    
    st.markdown(f"""
        <div style="
            background-color: {bg_color}; 
            padding: 35px; 
            border-radius: 20px; 
            border: 1px solid #444;
            border-left: 10px solid #FF4B4B; 
            margin-bottom: 25px; 
            box-shadow: 0 10px 20px {card_shadow};
            text-align: center;
        ">
            <p style="color: {sub_text}; margin-bottom: 10px; font-size: 1.1em; letter-spacing: 2px;">VOCABULARY QUIZ</p>
            <h2 style="color: {text_color}; margin: 15px 0; font-size: 2.2em;">
                請選出「 <span style="color: #FF4B4B; font-weight: 900; text-shadow: 0px 0px 10px rgba(255,75,75,0.3);">{q['word']}</span> 」的正確定義
            </h2>
            <div style="margin-top: 20px;">
                <span style="background-color: {label_bg}; padding: 6px 18px; border-radius: 25px; font-size: 0.9em; color: #FF4B4B; border: 1px solid #444; font-weight: bold;">
                    PART OF SPEECH: {q['pos']}
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 1. 四個選項按鈕
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
                        if not any(item['單字'] == q['word'] for item in st.session_state.wrong_answers):
                            st.session_state.wrong_answers.append({
                                "單字": q['word'], "詞性": q['pos'], "正確定義": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")
                            })
                    st.session_state.ans_revealed = True

    # 2. 【關鍵更新】解答統一顯示在按鈕下方
    if st.session_state.ans_revealed:
        st.write("---") # 分割線
        if st.session_state.is_correct:
            st.success(f"🎊 **回答正確！** 定義就是：{q['correct_ans']}")
        else:
            st.error(f"⚠️ **回答錯誤！** 正確答案應該是：**{q['correct_ans']}**")
        
        # 下一題按鈕置中顯示
        if st.button("➡️ 下一題 (Next Step)", type="primary", use_container_width=True):
            generate_question()
            st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 擴充你的單字資料庫")

    SCRIPT_URL = st.secrets["connections"]["gsheets"]["script_url"]
    
    with st.form("add_word_form", clear_on_submit=True):
        new_word = st.text_input("英文單字 (Word)")
        new_pos = st.selectbox("詞性 (POS)", ["n.", "v.", "adj.", "adv.", "prep.", "conj.", "phr."])
        new_def = st.text_input("中文定義 (Definition)")
        
        submit = st.form_submit_button("💾 儲存至雲端資料庫")
        
        if submit:
            if new_word and new_def:
                try:
                    payload = {
                        "method": "write", 
                        "word": new_word,
                        "pos": new_pos,
                        "definition": new_def
                    }
                    
                    import requests
                    with st.spinner("正在同步至 Google Sheets..."):
                        response = requests.post(SCRIPT_URL, json=payload, timeout=10)
                    
                    if response.status_code == 200:
                        st.success(f"🎉 成功加入單字：{new_word}！")
                        st.cache_data.clear()
                    else:
                        st.error(f"寫入失敗，Apps Script 回傳錯誤代碼: {response.status_code}")
                except Exception as e:
                    st.error(f"連線至 Apps Script 發生錯誤: {e}")
            else:
                st.warning("請填寫單字與定義。")

elif mode == "錯題複習":
    st.subheader("🔍 弱點分析：我的錯題本")
    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
        if st.button("🗑️ 清空記錄", use_container_width=True):
            st.session_state.wrong_answers = []
            st.rerun()
    else:
        st.info("目前沒有錯題記錄！")
