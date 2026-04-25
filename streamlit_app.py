import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests
import plotly.express as px
import re
import urllib.parse
import time
from gtts import gTTS
import io
import tempfile

# ==============================================================================
# 1. 頁面與持久化設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字練習", page_icon="📖", layout="wide")

@st.cache_resource
def get_global_progress():
    return {
        'score': 0,
        'total_answered': 0,
        'wrong_answers': [],
        'mastery_ids': set()
    }

progress = get_global_progress()

if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None

# ==============================================================================
# 🔊 自動發音函數 (JavaScript 注入)
# ==============================================================================
def speak_text(text):
    """Windows/macOS/iOS 兼容，按鈕觸發播放"""
    if not text:
        return

    # 過濾非英文與數字符號
    english_only = " ".join(re.findall(r'[a-zA-Z0-9\s\.,\?!\'\";:-]+', text))
    if not english_only.strip():
        st.warning("文字中沒有可發音的英文")
        return

    try:
        audio_fp = io.BytesIO()
        tts = gTTS(text=english_only, lang='en', slow=False)
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)  # ✅ 重置指標
        st.audio(audio_fp, format="audio/mp3")
    except Exception as e:
        st.error(f"發音失敗: {e}")

# 側邊欄設定
with st.sidebar:
    st.header("🎨 介面設定")
    theme_mode = st.selectbox("切換主題模式", ["深色模式 (Dark)", "淺色模式 (Light)"])
    quiz_mode_type = st.selectbox("📝 測驗題型", ["標準選擇題", "填空挑戰 (Cloze)"])
    auto_audio = st.checkbox("🔊 答題後自動發音", value=True)
    
    if theme_mode == "深色模式 (Dark)":
        main_bg, card_bg, text_color = "#0E1117", "#1E1E1E", "#FFFFFF"
        quiz_box_bg = "#1A2E44"
        ex_bg = "#262730"
    else:
        main_bg, card_bg, text_color = "#FFFFFF", "#F0F2F6", "#1F1F1F"
        quiz_box_bg = "#E1F5FE"
        ex_bg = "#F8F9FB"

    st.write("---")
    st.header("📈 學習統計")
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

# CSS 設定
st.markdown(f"""
    <style>
    .stApp {{ background-color: {main_bg} !important; color: {text_color} !important; }}
    .stButton>button {{ border-radius: 12px; height: 3.5em; border: 1px solid #444; background-color: {card_bg} !important; color: {text_color} !important; font-weight: bold; }}
    .quiz-container {{ background-color: {quiz_box_bg}; padding: 40px 20px; border-radius: 15px; text-align: center; margin-bottom: 25px; border: 1px solid #444; }}
    .quiz-word {{ font-size: 48px !important; font-weight: 800 !important; color: {text_color}; margin-bottom: 5px; }}
    .cloze-sentence {{ font-size: 24px !important; color: {text_color}; line-height: 1.5; }}
    .quiz-pos {{ font-size: 20px; color: #FF4B4B; font-weight: bold; }}
    .example-box {{ background-color: {ex_bg}; border-left: 5px solid #28a745; padding: 15px 20px; margin: 15px 0; border-radius: 8px; font-style: italic; color: {text_color}; line-height: 1.6; }}
    .point-box {{ background-color: #FFF3E0; border-left: 5px solid #FF9800; padding: 12px 20px; margin: 10px 0; border-radius: 8px; color: #E65100; font-weight: 500; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 核心函式
# ==============================================================================
def generate_question(source_df, target_state_key='quiz_data'):
    if source_df is None or source_df.empty: return
    try:
        # 確保填空題模式時，只抽有例句的單字
        if quiz_mode_type == "填空挑戰 (Cloze)":
            source_df = source_df[source_df['example'].notna() & (source_df['example'] != "")]
        
        target = source_df.sample(n=1).iloc[0]
        full_pool = st.session_state.get('full_df', pd.DataFrame())
        
        # 準備選項
        if quiz_mode_type == "標準選擇題":
            distractors = full_pool[full_pool['definition'] != target['definition']].sample(n=min(3, len(full_pool)-1))['definition'].tolist()
            correct_ans = target['definition']
        else: # 填空挑戰：選項是「單字」本身
            distractors = full_pool[full_pool['word'] != target['word']].sample(n=min(3, len(full_pool)-1))['word'].tolist()
            correct_ans = target['word']

        options = distractors + [correct_ans]
        random.shuffle(options)
        
        ex_val = str(target['example']) if 'example' in target and pd.notna(target['example']) else ""
        pt_val = str(target['point']) if 'point' in target and pd.notna(target['point']) else ""
        
        # 處理填空題題目文字
        cloze_text = ""
        if quiz_mode_type == "填空挑戰 (Cloze)" and ex_val:
            # 忽略大小寫替換關鍵字
            pattern = re.compile(re.escape(target['word']), re.IGNORECASE)
            cloze_text = pattern.sub(" _______ ", ex_val)

        st.session_state[target_state_key] = {
            'word': target['word'], 
            'correct_ans': correct_ans, 
            'pos': target['pos'], 
            'options': options,
            'example': ex_val,
            'point': pt_val,
            'cloze_text': cloze_text
        }
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

st.session_state.full_df = fetch_data()

# ==============================================================================
# 3. 介面路由
# ==============================================================================
with st.sidebar:
    mode = st.radio("🚀 功能模式切換", ["開始測驗", "錯題強化挑戰", "新增單字庫"])

st.title("📖 多益單字強化練習")

if mode == "開始測驗":
    if st.session_state.full_df.empty:
        st.warning("📭 單字庫為空。")
    else:
        if st.session_state.quiz_data is None: generate_question(st.session_state.full_df, 'quiz_data')
        q = st.session_state.quiz_data
        
        if q:
            # --- 題目顯示區 ---
            with st.container():
                if quiz_mode_type == "標準選擇題":
                    st.markdown(f'<div class="quiz-container"><div class="quiz-word">{q["word"]}</div><div class="quiz-pos">({q["pos"]})</div></div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="quiz-container"><div class="cloze-sentence">{q["cloze_text"]}</div><div class="quiz-pos">({q["pos"]})</div></div>', unsafe_allow_html=True)
            
            # --- 選項按鈕 ---
            cols = st.columns(2)
            for i, option in enumerate(q['options']):
                with cols[i % 2]:
                    if st.button(option, key=f"btn_{i}", use_container_width=True, disabled=st.session_state.ans_revealed):
                        progress['total_answered'] += 1
                        st.session_state.ans_revealed = True
                        if option == q['correct_ans']:
                            progress['score'] += 1
                            st.session_state.is_correct = True
                        else:
                            st.session_state.is_correct = False
                            if not any(item['word'] == q['word'] for item in progress['wrong_answers']):
                                progress['wrong_answers'].append({
                                    'word': q['word'], 'pos': q['pos'],
                                    'definition': q['word'], 'mastered': False
                                })
                        st.rerun()

            # --- 回饋區 ---
            if st.session_state.ans_revealed:
                if st.session_state.is_correct:
                    st.success("🎯 太棒了！回答正確！")
                else:
                    st.error(f"❌ 不對喔！正確答案是：**{q['correct_ans']}**")
                
                # --- 修改後的發音按鈕區 (單字 + 例句) ---
                c1, c2, _ = st.columns([1, 1, 3]) # 增加一欄給例句發音
                with c1:
                    if st.button("🔊 單字"): speak_text(q['word'])
                with c2:
                    if q['example']: # 有例句才顯示按鈕
                        if st.button("📢 例句"): speak_text(q['example'])

                if q['point']:
                    st.markdown(f'<div class="point-box"><b>📌 出題重點：</b>{q["point"]}</div>', unsafe_allow_html=True)

                if q['example']:
                    # 顯示例句文字
                    st.markdown(f"""
                        <div class="example-box">
                            <div class="example-label">💡 Usage Example:</div>
                            {q['example']}
                        </div>
                    """, unsafe_allow_html=True)
                
                if st.button("➡️ 下一題", type="primary", use_container_width=True):
                    generate_question(st.session_state.full_df, 'quiz_data')
                    st.rerun()

# --- 模式 3：新增單字庫 ---
elif mode == "新增單字庫":
    st.subheader("➕ 擴充雲端單字庫")
    url = st.secrets["connections"]["gsheets"]["script_url"]
    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1: w = st.text_input("英文單字")
        with col2: p = st.selectbox("詞性", ["n.", "v.", "adj.", "adv.", "phr."])
        
        d = st.text_input("中文定義")
        
        # 新增 point 欄位
        pt = st.text_area("出題重點 (Point)", placeholder="例如：常與介系詞 with 連用...")
        
        ex = st.text_area("例句 (Example Sentence)", placeholder="請輸入此單字的用法例句...")
        
        if st.form_submit_button("💾 儲存並同步"):
            if w and d:
                payload = {
                    "method": "write", 
                    "word": w, 
                    "pos": p, 
                    "definition": d, 
                    "point": pt, 
                    "example": ex
                }
                try:
                    res = requests.post(url, json=payload)
                    if res.status_code == 200:
                        st.success(f"✅ 『{w}』及其例句已送出！")
                        st.cache_data.clear()
                except Exception as e: 
                    st.error(f"錯誤：{e}")
