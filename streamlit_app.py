import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime

# ==============================================================================
# 第一部分：【資料連線與全域初始化】
# ==============================================================================
# 重要：先給 df 一個預設值，防止後續 generate_question 找不到變數
df = pd.DataFrame() 

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="1m") 
except Exception as e:
    st.error(f"⚠️ 無法連線至 Google Sheets，請檢查 Secrets 設定。")
    # 這裡確保即使出錯，df 也是一個空的 DataFrame 而不是 None
    df = pd.DataFrame() 

# ==============================================================================
# 第二部分：【函式定義】
# ==============================================================================
def generate_question():
    # 使用 global 關鍵字強制函式去抓取外面的 df 變數
    global df 
    
    # 增加檢查：如果 df 不存在或是空的就跳出
    if df is None or df.empty:
        return
    
    try:
        target = df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        # 確保資料量足夠生成干擾項
        if len(df) >= 4:
            distractors = df[df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
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
        st.error(f"生成題目時發生錯誤: {e}")

# 在主流程中，確保只有在 df 有資料時才觸發生成
if st.session_state.quiz_data is None and not df.empty:
    generate_question()
# ==============================================================================
# 第三部分：【核心邏輯與狀態管理】
# ==============================================================================
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

def generate_question():
    global df # 確保能讀取到全域的 df
    if df.empty:
        return
    
    target = df.sample(n=1).iloc[0]
    correct_ans = target['definition']
    # 確保資料量足夠生成干擾項
    if len(df) >= 4:
        distractors = df[df['definition'] != correct_ans].sample(n=3)['definition'].tolist()
    else:
        distractors = ["選項A", "選項B", "選項C"]
        
    options = distractors + [correct_ans]
    random.shuffle(options)
    st.session_state.quiz_data = {'word': target['word'], 'correct_ans': correct_ans, 'pos': target['pos'], 'options': options}
    st.session_state.ans_revealed = False
    st.session_state.is_correct = None

# 如果資料已就緒且沒題目，則自動生成
if st.session_state.quiz_data is None and not df.empty:
    generate_question()

# ==============================================================================
# 第四部分：【側邊欄與 UI 模式切換】
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

# --- 模式 1：開始測驗 ---
if mode == "開始測驗":
    if df.empty:
        st.warning("📭 單字庫目前沒有資料，請先新增單字。")
    elif st.session_state.quiz_data:
        q = st.session_state.quiz_data
        
        # 題目卡片
        st.markdown(f"""
            <div style="
                background-color: {card_bg}; 
                padding: 35px; 
                border-radius: 20px; 
                border: 1px solid #444;
                border-left: 10px solid #FF4B4B; 
                margin-bottom: 25px; 
                box-shadow: 0 10px 20px {card_shadow};
                text-align: center;
            ">
                <p style="color: {sub_text}; margin-bottom: 10px; font-size: 1.1em; letter-spacing: 2px;">VOCABULARY QUIZ</p>
                <h2 style="color: {text_color} !important; margin: 15px 0; font-size: 2.2em;">
                    請選出「 <span style="color: #FF4B4B; font-weight: 900;">{q['word']}</span> 」的正確定義
                </h2>
                <div style="margin-top: 20px;">
                    <span style="background-color: {label_bg}; padding: 6px 18px; border-radius: 25px; font-size: 0.9em; color: #FF4B4B; border: 1px solid #444; font-weight: bold;">
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
                            st.session_state.is_correct = True
                            st.balloons()
                        else:
                            st.session_state.is_correct = False
                            if not any(item['單字'] == q['word'] for item in st.session_state.wrong_answers):
                                st.session_state.wrong_answers.append({
                                    "單字": q['word'], "詞性": q['pos'], "正確定義": q['correct_ans'], "時間": datetime.now().strftime("%H:%M")
                                })
                        st.session_state.ans_revealed = True

        if st.session_state.ans_revealed:
            st.write("---")
            if st.session_state.is_correct:
                st.success(f"🎊 **回答正確！** 定義就是：{q['correct_ans']}")
            else:
                st.error(f"⚠️ **回答錯誤！** 正確答案應該是：**{q['correct_ans']}**")
            
            if st.button("➡️ 下一題 (Next Step)", type="primary", use_container_width=True):
                generate_question()
                st.rerun()

# --- 模式 2：新增單字庫 ---
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
                    payload = {"method": "write", "word": new_word, "pos": new_pos, "definition": new_def}
                    with st.spinner("正在同步..."):
                        response = requests.post(SCRIPT_URL, json=payload, timeout=10)
                    if response.status_code == 200:
                        st.success(f"🎉 成功加入：{new_word}！")
                        st.cache_data.clear()
                    else:
                        st.error("寫入失敗。")
                except Exception as e:
                    st.error(f"連線錯誤: {e}")
            else:
                st.warning("請填寫內容。")

# --- 模式 3：錯題複習 ---
elif mode == "錯題複習":
    st.subheader("🔍 弱點分析：我的錯題本")
    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
        if st.button("🗑️ 清空記錄", use_container_width=True):
            st.session_state.wrong_answers = []
            st.rerun()
    else:
        st.info("目前沒有錯題記錄！")
