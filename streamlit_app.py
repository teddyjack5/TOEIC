if mode == "測驗":

    if not user_id:
        st.warning("請輸入User ID")
        st.stop()

    # =========================
    # Session State 初始化
    # =========================
    if "state" not in st.session_state:
        st.session_state.state = "q"
        st.session_state.score = 0
        st.session_state.streak = 0
        st.session_state.count = 1
        st.session_state.q = None
        st.session_state.wrong_list = []

    TOTAL = 10

    # =========================
    # 出題（🔥 已整合 Cloze）
    # =========================
    if st.session_state.q is None:

        if practice_mode == "填空":
            st.session_state.q = get_cloze_question(user_id)
        else:
            st.session_state.q = get_weighted_question(user_id, practice_mode)

    q = st.session_state.q

    if q is None:
        st.warning("目前沒有題目")
        st.stop()

    # =========================
    # 進度條
    # =========================
    st.progress(min(st.session_state.count / TOTAL, 1.0))

    st.markdown(f"🏆 {st.session_state.score}　🔥 {st.session_state.streak}")

    # =========================
    # 題目顯示（🔥 Cloze / 單字統一）
    # =========================
    if practice_mode == "填空":
        display_text = q["sentence"]
    else:
        display_text = q["definition"]

    st.markdown(f"""
    <div class="card">
        <div class="big">{display_text}</div>
    </div>
    """, unsafe_allow_html=True)

    # =========================
    # 作答
    # =========================
    if st.session_state.state == "q":

        for opt in q["options"]:
            if st.button(opt):

                st.session_state.selected = opt
                st.session_state.state = "result"
                st.rerun()

    # =========================
    # 結果畫面
    # =========================
    else:

        # -------------------------
        # 正確答案統一處理
        # -------------------------
        if practice_mode == "填空":
            correct = q["answer"]
        else:
            correct = q["correct"]

        selected = st.session_state.selected
        is_correct = selected == correct

        # =========================
        # 錯題紀錄（🔥 修好）
        # =========================
        if not is_correct:
            st.session_state.wrong_list.append(q)

        # update score
        if is_correct:
            st.success("✅ Correct")
            st.session_state.score += 10
            st.session_state.streak += 1
        else:
            st.error(f"❌ {correct}")
            st.session_state.streak = 0

        # =========================
        # 結果卡片
        # =========================
        st.markdown("### 📊 Answer Result")

        st.markdown(f"""
        <div style="
            background:#111827;
            padding:18px;
            border-radius:15px;
            color:white;
            text-align:center;
        ">
            {'🎉 正確！' if is_correct else '📌 再加油'}
        </div>
        """, unsafe_allow_html=True)

        # =========================
        # 📖 例句（分離）
        # =========================
        with st.expander("💡 查看例句", expanded=False):
            st.markdown(f"""
            <div style="
                background:#1F2937;
                padding:15px;
                border-radius:12px;
                color:white;
            ">
                {q.get("example", "")}
            </div>
            """, unsafe_allow_html=True)

        # =========================
        # 📌 考點
        # =========================
        with st.expander("📌 查看考點", expanded=False):
            st.markdown(f"""
            <div style="
                background:#0F172A;
                padding:15px;
                border-radius:12px;
                color:white;
            ">
                {q.get("point", "")}
            </div>
            """, unsafe_allow_html=True)

        # =========================
        # 🔊 發音
        # =========================
        st.markdown("### 🔊 發音")

        col1, col2 = st.columns(2)

        with col1:
            create_audio_button(q.get("word", ""), "🔊 單字", theme_mode)

        with col2:
            create_audio_button(q.get("example", ""), "📢 例句", theme_mode)

        # =========================
        # 下一題
        # =========================
        if st.button("➡️ 下一題"):

            if st.session_state.count >= TOTAL:
                st.session_state.state = "done"
                st.rerun()

            # reset
            st.session_state.q = None
            st.session_state.state = "q"
            st.session_state.count += 1
            st.rerun()


# =========================
# 🎯 完成畫面
# =========================
if st.session_state.get("state") == "done":

    total = st.session_state.count
    wrongs = len(st.session_state.wrong_list)
    correct = total - wrongs

    acc = int((correct / total) * 100)

    st.markdown("## 🎉 測驗完成！")

    st.metric("正確率", f"{acc}%")
    st.metric("答對", correct)
    st.metric("錯題", wrongs)

    # 評語
    if acc >= 90:
        st.success("🔥 太強了！")
    elif acc >= 70:
        st.info("👍 不錯，建議複習錯題")
    else:
        st.warning("📌 建議加強複習")

    # =========================
    # 錯題回顧
    # =========================
    if wrongs > 0:
        st.markdown("## 📚 錯題回顧")

        for i, item in enumerate(st.session_state.wrong_list):

            with st.expander(f"{i+1}. {item.get('word','')}"):

                st.write("📖", item.get("definition", ""))
                st.write("💡", item.get("example", ""))

                col1, col2 = st.columns(2)

                with col1:
                    create_audio_button(item.get("word", ""), "🔊 單字", theme_mode)

                with col2:
                    create_audio_button(item.get("example", ""), "📢 例句", theme_mode)

    # restart
    if st.button("🔁 再挑戰一次"):

        st.session_state.state = "q"
        st.session_state.score = 0
        st.session_state.streak = 0
        st.session_state.count = 1
        st.session_state.q = None
        st.session_state.wrong_list = []

        st.rerun()
