import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
import plotly.express as px

# ==============================================================================
# 1. 頁面與持久化設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字戰情室", page_icon="📖", layout="wide")

# 【核心持久化邏輯】利用 cache_resource 儲存進度，不受重新整理影響
@st.cache_resource
def get_global_progress():
    return {
        'score': 0,
        'total_answered': 0,
        'wrong_answers': [],
        'mastery_ids': set() # 記錄已掌握的單字
    }

progress = get_global_progress()

# 初始化 Session State (僅用於控制 UI 顯示，不存核心分數)
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'review_quiz_data' not in st.session_state: st.session_state.review_quiz_data = None
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None

# 側邊欄設定
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    
    if theme_mode == "深色模式 (Dark)":
        main_bg, card_bg, text_color, label_bg = "#0E1117", "#1E1E1E", "#FFFFFF", "#333333"
        quiz_box_bg = "#1A2E44"
    else:
        main_bg, card_bg, text_color, label_bg = "#FFFFFF", "#F0F2F6", "#1F1F1F", "#E0E0E0"
        quiz_box_bg = "#E1F5FE"

    st.write("---")
    st.header("📈 學習統計 (已持久化)")
    # 從全局 progress 讀取數據
    if progress['total_answered'] > 0:
        acc_data = pd.DataFrame({
            "結果": ["正確", "錯誤"],
            "題數": [progress['score'], progress['total_answered'] - progress['score']]
        })
        fig = px.pie(acc_data, values='題數', names='結果', 
                     color_discrete_sequence=['#28a745', '#dc3545'], hole=0.5)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=200, showlegend=False,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
        st.metric("當前正確率", f"{(progress['score']/progress['total_answered'])*100:.1f}%")
    else:
        st.info("尚無數據")

# CSS 樣式
st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg} !important; color: {text_color} !important; }}
    .stButton>button {{ border-radius: 12px; height: 3.5em; border: 1px solid #444; background-color: {card_bg} !important; color: {text_color} !important; font-weight: bold; }}
    .quiz-container {{ background-color: {quiz_box_bg}; padding: 40px 20px; border-radius: 15px; text-align: center; margin-bottom: 25px; border: 1px solid #444; }}
    .quiz-word {{ font-size: 48px !important; font-weight: 800 !important; color: {text_color}; margin-bottom: 5px; }}
    .quiz-pos {{ font-size: 20px; color: #FF4B4B; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 核心邏輯
# ==============================================================================
def generate_question(source_df, target_state_key='quiz_data'):
    if source_df is None or source_df.empty:
        st.session_state[target_state_key] = None
        return
    try:
        target = source_df.sample(n=1).iloc[0]
        correct_ans = target['definition']
        full_pool = st.session_state.get('full_df', pd.DataFrame())
        distractors = full_pool[full_pool['definition'] != correct_ans].sample(n=min(3, len(full_pool)-1))['definition'].tolist()
        options = distractors + [correct_ans]
        random.shuffle(options)
        st.session_state[target_state_key] = {'word': target['word'], 'correct_ans': correct_ans, 'pos': target['pos'], 'options': options}
        st.session_state.ans_revealed = False
        st.session_state.is_correct = None
    except Exception as e:
        st.error(f"生成失敗：{e}")

@st.cache_data(ttl=60)
def fetch_data():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()
    except: return pd.DataFrame()

# 儲存全域資料至 session 僅供抽題參考
st.session_state.full_df = fetch_data()

# ==============================================================================
# 3. 介面路由
# ==============================================================================
with st.sidebar:
    mode = st.radio("🚀 功能模式切換", ["開始測驗", "錯題強化挑戰", "新增單字庫"])
    if st.button("♻️ 手動重置所有進度", use_container_width=True):
        # 清空全局快取
        progress['score'] = 0
        progress['total_answered'] = 0
        progress['wrong_answers'] = []
        progress['mastery_ids'] = set()
        st.session_state.quiz_data = None
        st.rerun()

st.title("📖 多益單字強化戰情室")

if mode == "開始測驗":
    if st.session_state.full_df.empty:
        st.warning("📭 單字庫為空。")
    else:
        if st.session_state.quiz_data is None: generate_question(st.session_state.full_df, 'quiz_data')
        q = st.session_state.quiz_data
        if q:
            st.markdown(f'<div class="quiz-container"><div class="quiz-word">{q["word"]}</div><div class="quiz-pos">({q["pos"]})</div></div>', unsafe_allow_html=True)
            cols = st.columns(2)
            for i, option in enumerate(q['options']):
                with cols[i % 2]:
                    if st.button(option, key=f"btn_{i}", use_container_width=True, disabled=st.session_state.ans_revealed):
                        # 更新全局進度
                        progress['total_answered'] += 1
                        if option == q['correct_ans']:
                            progress['score'] += 1
                            st.session_state.is_correct = True
                        else:
                            st.session_state.is_correct = False
                            if not any(item['word'] == q['word'] for item in progress['wrong_answers']):
                                progress['wrong_answers'].append({
                                    'word': q['word'], 'pos': q['pos'], 'definition': q['correct_ans'], 'mastered': False
                                })
                        st.session_state.ans_revealed = True
                        st.rerun()

            if st.session_state.ans_revealed:
                if st.session_state.is_correct: st.success("🎯 回答正確！")
                else: st.error(f"❌ 錯誤！正確答案：{q['correct_ans']}")
                if st.button("➡️ 下一題", type="primary", use_container_width=True):
                    generate_question(st.session_state.full_df, 'quiz_data')
                    st.rerun()

elif mode == "錯題強化挑戰":
    st.subheader("🔥 弱點針對訓練")
    if not progress['wrong_answers']:
        st.info("目前沒有錯題紀錄。")
    else:
        # 從全局 progress 讀取尚未掌握的單字
        pending_list = [item for item in progress['wrong_answers'] if item['word'] not in progress['mastery_ids']]
        pending_df = pd.DataFrame(pending_list)
        
        if pending_df.empty:
            st.balloons()
            st.success("✨ 所有錯題皆已挑戰成功！")
        else:
            if st.session_state.review_quiz_data is None: generate_question(pending_df, 'review_quiz_data')
            rq = st.session_state.review_quiz_data
            if rq:
                st.markdown(f'<div class="quiz-container" style="border-top: 5px solid #FFC107;"><div class="quiz-word">{rq["word"]}</div><div class="quiz-pos">({rq["pos"]})</div></div>', unsafe_allow_html=True)
                cols = st.columns(2)
                for i, option in enumerate(rq['options']):
                    with cols[i % 2]:
                        if st.button(option, key=f"rev_{i}", use_container_width=True):
                            if option == rq['correct_ans']:
                                st.toast(f"✅ 成功掌握：{rq['word']}！")
                                progress['mastery_ids'].add(rq['word'])
                                st.session_state.review_quiz_data = None
                                st.rerun()
                            else: st.error("選錯了，再想一下！")
                if st.button("⏭️ 跳過此題", use_container_width=True):
                    st.session_state.review_quiz_data = None
                    st.rerun()
        
        st.write("---")
        with st.expander("🔍 查看歷史錯題本 (回顧歷程)", expanded=False):
            if progress['wrong_answers']:
                history_df = pd.DataFrame(progress['wrong_answers'])
                history_df['狀態'] = history_df['word'].apply(lambda x: "✅ 已掌握" if x in progress['mastery_ids'] else "❌ 待加強")
                st.table(history_df[['word', 'pos', 'definition', '狀態']])

elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    try:
        url = st.secrets["connections"]["gsheets"]["script_url"]
        with st.form("add_form", clear_on_submit=True):
            w = st.text_input("英文單字"); p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."]); d = st.text_input("定義")
            if st.form_submit_button("💾 儲存並同步"):
                if w and d:
                    res = requests.post(url, json={"method": "write", "word": w, "pos": p, "definition": d})
                    st.success(f"✅ 『{w}』已送出！"); st.cache_data.clear()
    except: st.error("請確認 Secrets 設定。")
