import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
import requests

# ==============================================================================
# 1. 頁面基本設定
# ==============================================================================
st.set_page_config(page_title="小鐵的多益單字測驗", page_icon="📖", layout="wide")

# Session State 初始化
if 'quiz_data' not in st.session_state: st.session_state.quiz_data = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'total_answered' not in st.session_state: st.session_state.total_answered = 0
if 'ans_revealed' not in st.session_state: st.session_state.ans_revealed = False
if 'is_correct' not in st.session_state: st.session_state.is_correct = None
if 'wrong_answers' not in st.session_state: st.session_state.wrong_answers = []

# ==============================================================================
# 2. 核心函式
# ==============================================================================
def generate_question(source_df: pd.DataFrame):
    if source_df is None or source_df.empty:
        return

    try:
        target = source_df.sample(n=1).iloc[0]
        correct_ans = target['definition']

        pool = source_df[source_df['definition'] != correct_ans]['definition']

        if len(pool) >= 3:
            distractors = pool.sample(n=3).tolist()
        else:
            distractors = pool.tolist()
            distractors += ["（不足選項）"] * (3 - len(distractors))

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
        st.error(f"抽題發生錯誤：{e}")

# ==============================================================================
# 3. 資料載入
# ==============================================================================
@st.cache_data(ttl=60)
def get_data_from_gsheets():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        return conn.read()
    except Exception:
        return pd.DataFrame()

df = get_data_from_gsheets()

# 初始題目
if st.session_state.quiz_data is None and not df.empty:
    generate_question(df)

# ==============================================================================
# 4. UI
# ==============================================================================
st.title("📖 多益單字戰情室")

with st.sidebar:
    st.header("📊 學習狀態")

    if st.session_state.total_answered > 0:
        rate = st.session_state.score / st.session_state.total_answered
        st.metric("正確率", f"{rate:.0%}")
    else:
        st.metric("正確率", "0%")

    mode = st.radio("🚀 選擇功能", ["開始測驗", "新增單字庫", "錯題複習"])

    if st.button("♻️ 重置進度"):
        st.session_state.update({
            "quiz_data": None,
            "score": 0,
            "total_answered": 0,
            "wrong_answers": []
        })
        st.cache_data.clear()
        st.rerun()

# ==============================================================================
# 測驗模式
# ==============================================================================
if mode == "開始測驗":

    if df.empty:
        st.warning("📭 單字庫是空的")
    elif st.session_state.quiz_data:

        q = st.session_state.quiz_data

        st.info(f"請選出「{q['word']}」({q['pos']}) 的正確定義：")

        for i, option in enumerate(q['options']):
            if st.button(option, key=f"btn_{i}", use_container_width=True,
                         disabled=st.session_state.ans_revealed):

                st.session_state.total_answered += 1

                if option == q['correct_ans']:
                    st.session_state.score += 1
                    st.session_state.is_correct = True
                    st.balloons()
                else:
                    st.session_state.is_correct = False

                    entry = {
                        "單字": q['word'],
                        "正確答案": q['correct_ans']
                    }

                    if entry not in st.session_state.wrong_answers:
                        st.session_state.wrong_answers.append(entry)

                st.session_state.ans_revealed = True
                st.rerun()

        # 顯示結果
        if st.session_state.ans_revealed:
            if st.session_state.is_correct:
                st.success("正確！")
            else:
                st.error(f"錯誤！正確答案是：{q['correct_ans']}")

            if st.button("➡️ 下一題", type="primary", use_container_width=True):
                generate_question(df)
                st.rerun()

# ==============================================================================
# 新增單字
# ==============================================================================
elif mode == "新增單字庫":

    st.subheader("➕ 擴充資料庫")

    try:
        script_url = st.secrets["connections"]["gsheets"]["script_url"]

        with st.form("add_form", clear_on_submit=True):
            w = st.text_input("Word")
            p = st.text_input("POS")
            d = st.text_input("Definition")

            if st.form_submit_button("儲存"):
                if w and d:
                    try:
                        res = requests.post(
                            script_url,
                            json={
                                "method": "write",
                                "word": w,
                                "pos": p,
                                "definition": d
                            }
                        )

                        if res.status_code == 200:
                            st.success("寫入成功！")
                            st.cache_data.clear()
                        else:
                            st.error(f"寫入失敗：{res.status_code}")

                    except Exception as e:
                        st.error(f"請求失敗：{e}")
                else:
                    st.warning("請填寫完整")

    except:
        st.error("請確認 secrets 設定")

# ==============================================================================
# 錯題複習
# ==============================================================================
elif mode == "錯題複習":

    st.subheader("🔍 錯題記錄")

    if st.session_state.wrong_answers:
        st.table(pd.DataFrame(st.session_state.wrong_answers))
    else:
        st.info("目前沒有錯題！")
