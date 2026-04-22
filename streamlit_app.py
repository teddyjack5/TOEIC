import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
from datetime import datetime
import plotly.express as px

# ==============================================================================
# 1. 頁面與主題設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# 初始化 Session State (SIT 防護機制)
state_defaults = {
    'df': pd.DataFrame(),
    'quiz_data': None,
    'score': 0,
    'total_answered': 0,
    'ans_revealed': False,
    'is_correct': None,
    'wrong_answers': [],
    'review_quiz_data': None # 專門給錯題模式使用的題目暫存
}
for key, value in state_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# 側邊欄：主題與統計
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    
    if theme_mode == "深色模式 (Dark)":
        main_bg, card_bg, text_color, label_bg = "#0E1117", "#1E1E1E", "#FFFFFF", "#333333"
    else:
        main_bg, card_bg, text_color, label_bg = "#FFFFFF", "#F0F2F6", "#1F1F1F", "#E0E0E0"

    st.write("---")
    st.header("📈 學習數據")
    if st.session_state.total_answered > 0:
        acc_data = {
            "結果": ["正確", "錯誤"],
            "題數": [st.session_state.score, st.session_state.total_answered - st.session_state.score]
        }
        fig = px.pie(acc_data, values='題數', names='結果', 
                     color_discrete_sequence=['#28a745', '#dc3545'], hole=0.5)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=200, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.metric("當前正確率", f"{(st.session_state.score/st.session_state.total_answered)*100:.1f}%")
    else:
        st.info("尚無測驗數據")

# CSS 強制覆蓋
st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg} !important; color: {text_color} !important; }}
    .stButton>button {{ border-radius: 12px; height: 3em; border: 1px solid #444; background-color: {card_bg} !important; color: {text_color} !important; }}
    .stButton>button:hover {{ border-color: #FF4B4B !important; color: #FF4B4B !important; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 核心邏輯函式
# ==============================================================================
def generate_question(source_df, target_state_key='quiz_data'):
    """通用題目生成器，支援從總庫或錯題庫抽題"""
    if source_df is None or source_df.empty:
        return
    
    try:
        target = source_df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        
        # 準備干擾項：優先從總庫抽，確保選項夠多
        full_df = st.session_state.df
        distractors = full_df[full_df['definition'] != correct_ans].sample(n=min(3, len(full_df)-1))['definition'].tolist()
        
        options = distractors + [correct_ans]
        random.shuffle(options)
        
        st.session_state[target_state_key] = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options
        }
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"題目生成失敗: {e}")

@st.cache_data(ttl=60)
def fetch_data():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()
    except:
        return pd.DataFrame()

# 資料讀取與初始觸發
st.session_state.df = fetch_data()

# ==============================================================================
# 3. UI 模式路由
# ==============================================================================
with st.sidebar:
    mode = st.radio("🚀 選擇功能模式", ["開始測驗", "錯題強化測驗", "新增單字庫"])
    if st.button("♻️ 重置所有進度", use_container_width=True):
        st.session_state.update({"score": 0, "total_answered": 0, "wrong_answers": [], "quiz_data": None})
        st.cache_data.clear()
        st.rerun()

st.title("📖 多益 (TOEIC) 單字強化戰情室")

# --- 模式 1：開始測驗 ---
if mode == "開始測驗":
    if st.session_state.df.empty:
        st.warning("📭 單字庫為空，請先新增單字。")
    else:
        if st.session_state.quiz_data is None:
            generate_question(st.session_state.df)
            
        q = st.session_state.quiz_data
        if q:
            st.markdown(f"""
                <div style="background-color: {card_bg}; padding: 30px; border-radius: 20px; border-left: 10px solid #FF4B4B; text-align: center; border: 1px solid #444;">
                    <h2 style="color: {text_color};">「 {q['word']} 」的正確定義是？</h2>
                    <span style="background-color: {label_bg}; padding: 4px 12px; border-radius: 10px; color: #FF4B4B; font-weight: bold;">{q['pos']}</span>
                </div>
            """, unsafe_allow_html=True)
            st.write("")

            cols = st.columns(2)
            for i, option in enumerate(q['options']):
                with cols[i % 2]:
                    if st.button(option, key=f"btn_{i}", use_container_width=True, disabled=st.session_state.ans_revealed):
                        st.session_state.total_answered += 1
                        if option == q['correct_ans']:
                            st.session_state.score += 1
                            st.session_state.is_correct = True
                        else:
                            st.session_state.is_correct = False
                            if not any(item['word'] == q['word'] for item in st.session_state.wrong_answers):
                                st.session_state.wrong_answers.append(q)
                        st.session_state.ans_revealed = True
                        st.rerun()

            if st.session_state.ans_revealed:
                if st.session_state.is_correct: st.success("🎯 回答正確！")
                else: st.error(f"❌ 答錯了！正確答案：{q['correct_ans']}")
                
                if st.button("➡️ 下一題", type="primary", use_container_width=True):
                    generate_question(st.session_state.df)
                    st.rerun()

# --- 模式 2：錯題強化 (Quiz 模式) ---
elif mode == "錯題強化測驗":
    st.subheader("🔥 針對弱點進行挑戰")
    if not st.session_state.wrong_answers:
        st.info("🎉 目前沒有錯題紀錄，太優秀了！")
    else:
        # 將錯題清單轉為 DF
        wrong_df = pd.DataFrame(st.session_state.wrong_answers)
        
        # 這裡使用獨立的 state key 'review_quiz_data'
        if st.session_state.review_quiz_data is None:
            generate_question(wrong_df, 'review_quiz_data')
            
        rq = st.session_state.review_quiz_data
        if rq:
            st.warning(f"複習單字：{rq['word']}")
            cols = st.columns(2)
            for i, option in enumerate(rq['options']):
                with cols[i % 2]:
                    if st.button(option, key=f"rev_{i}", use_container_width=True):
                        if option == rq['correct_ans']:
                            st.success("這次記住了！")
                            # 答對了從錯題本移除 (Anki 邏輯：掌握後移除)
                            st.session_state.wrong_answers = [item for item in st.session_state.wrong_answers if item['word'] != rq['word']]
                            generate_question(pd.DataFrame(st.session_state.wrong_answers), 'review_quiz_data')
                            st.rerun()
                        else:
                            st.error("還是不對喔，再接再厲！")
            
            if st.button("跳過此題"):
                generate_question(wrong_df, 'review_quiz_data')
                st.rerun()
        
        st.write("---")
        with st.expander("查看完整錯題清單"):
            st.table(wrong_df[['word', 'pos', 'correct_ans']])

# --- 模式 3：新增單字庫 ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    try:
        url = st.secrets["connections"]["gsheets"]["script_url"]
        with st.form("add_form", clear_on_submit=True):
            w = st.text_input("英文單字")
            p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
            d = st.text_input("中文定義")
            if st.form_submit_button("💾 儲存並同步"):
                if w and d:
                    res = requests.post(url, json={"method": "write", "word": w, "pos": p, "definition": d})
                    if res.status_code == 200:
                        st.success(f"✅ {w} 已成功加入！")
                        st.cache_data.clear()
                    else: st.error("寫入失敗，請檢查 Script 設定。")
                else: st.warning("請填寫內容。")
    except:
        st.error("請確認 Secrets 中的 script_url。")
