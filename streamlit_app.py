import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from datetime import datetime

# ==============================================================================
# 第一部分：【頁面設定與資料連線】
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 自定義 CSS：強化深色模式與紅黑對比
st.markdown("""
    <style>
    .stApp { background-color: #0E1117; }
    .stButton>button { border-radius: 10px; font-weight: bold; height: 3.5em; border: 1px solid #333; }
    .stButton>button:hover { border-color: #FF4B4B; color: #FF4B4B; }
    /* 文字輸入框樣式 */
    .stTextInput>div>div>input { background-color: #1E1E1E; color: white; border: 1px solid #333; }
    </style>
""", unsafe_allow_html=True)

st.title("📖 多益 (TOEIC) 單字強化戰情室")

# 建立 Google Sheets 連線
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="0") # 即時讀取
except Exception as e:
    st.error("無法連線至 Google Sheets，請檢查 Secrets 設定。")
    st.stop()

# ==============================================================================
# 第二部分：【核心邏輯與狀態管理】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
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

if st.session_state.quiz_data is None: generate_question()

# ==============================================================================
# 第三部分：【側邊欄導航】
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

# ==============================================================================
# 第四部分：【主畫面 UI】
# ==============================================================================

if mode == "開始測驗":
    q = st.session_state.quiz_data
    
    # 題目卡片：深色底 + 白色標題 + 紅色單字
    st.markdown(f"""
        <div style="
            background-color: #1E1E1E; 
            padding: 40px; 
            border-radius: 20px; 
            border: 1px solid #333;
            border-left: 10px solid #FF4B4B; 
            margin-bottom: 30px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            text-align: center;
        ">
            <p style="color: #888888; margin-bottom: 10px; font-size: 1.1em; letter-spacing: 2px; font-weight: bold;">VOCABULARY QUIZ</p>
            <h2 style="color: #FFFFFF; margin: 15px 0; font-size: 2.2em; line-height: 1.4;">
                請選出「 <span style="color: #FF4B4B; font-weight: 900; text-shadow: 0px 0px 15px rgba(255,75,75,0.4);">{q['word']}</span> 」的正確定義
            </h2>
            <div style="margin-top: 20px;">
                <span style="background-color: #333333; padding: 6px 20px; border-radius: 25px; font-size: 0.9em; color: #FF4B4B; border: 1px solid #444; font-weight: bold;">
                    PART OF SPEECH: {q['pos']}
                </span>
            </div>
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
                        st.balloons()
                        st.success("✅ Excellent! 回答正確")
                    else:
                        st.error(f"❌ 答錯了！正確答案是：{q['correct_ans']}")
                        if not any(item['單字'] == q['word'] for item in st.session_state.wrong_answers):
                            st.session_state.wrong_answers.append({
                                "單字": q['word'], "詞性": q['pos'], "正確定義": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")
                            })
                    st.session_state.ans_revealed = True

    if st.session_state.ans_revealed:
        if st.button("➡️ 下一題 (Next)", type="primary", use_container_width=True):
            generate_question()
            st.rerun()

elif mode == "新增單字庫":
    st.subheader("➕ 擴充你的單字資料庫")
    # 修正後的表單語法
    with st.form("add_word_form", clear_on_submit=True):
        new_word = st.text_input("英文單字 (Word)")
        new_pos = st.selectbox("詞性 (POS)", ["n.", "v.", "adj.", "adv.", "prep.", "conj.", "phr."])
        new_def = st.text_input("中文定義 (Definition)")
        
        # 修正這裡：函式名稱為 form_submit_button
        submit = st.form_submit_button("💾 儲存至雲端資料庫")
        
        if submit:
            if new_word and new_def:
                try:
                    new_row = pd.DataFrame([{"word": new_word, "pos": new_pos, "definition": new_def}])
                    updated_df = pd.concat([df, new_row], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=updated_df)
                    st.success(f"🎉 成功加入單字：{new_word}！")
                    st.cache_data.clear() # 清除快取以讀取新資料
                except Exception as e:
                    st.error(f"儲存失敗: {e}")
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

st.write("---")
st.caption("Designed for TOEIC Mastery | 2026 Edition")
