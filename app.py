import streamlit as st
import google.generativeai as genai

# アプリのページ設定
st.set_page_config(page_title="業務プロセス暗黙知抽出アプリ", layout="wide")

st.title("🧠 業務プロセス暗黙知抽出アプリ (インプット用)")
st.write("ベテラン社員の頭の中にある「判断基準」や「例外処理」をAIとの対話で引き出し、プロセス図を自動生成します。")

# サイドバー: APIキーの設定
st.sidebar.header("設定")
api_key = st.sidebar.text_input("Gemini APIキーを入力してください", type="password")

# セッション状態（データ保持）の初期化
if "phase" not in st.session_state:
    st.session_state.phase = "setup"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "context_data" not in st.session_state:
    st.session_state.context_data = ""

def init_gemini():
    if not api_key:
        st.warning("左のサイドバーからAPIキーを入力してください。")
        st.stop()
    genai.configure(api_key=api_key)
    
    try:
        # ★最強アプローチ：利用可能なモデルを自動で検索して取得する★
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if not available_models:
            st.error("利用可能なAIモデルが見つかりません。APIキーが正しくない可能性があります。")
            st.stop()
            
        # リストの中から最適なモデル（flashやpro）を自動選択
        target_model = available_models[0] # デフォルトは最初に見つかったもの
        for m in available_models:
            if "flash" in m or "pro" in m:
                target_model = m
                break
                
        # 見つかったモデルで初期化
        model = genai.GenerativeModel(target_model)
        st.session_state.chat_session = model.start_chat(history=[])
        
    except Exception as e:
        st.error(f"AIの初期設定でエラーが発生しました: {e}")
        st.stop()

# -------------------------------------------------------------------
# フェーズ1: 基本情報の入力
# -------------------------------------------------------------------
if st.session_state.phase == "setup":
    st.subheader("1. 対象業務の基本情報入力")
    task_name = st.text_input("対象業務 (例: 新規案件の見積もり)")
    customer_type = st.text_input("顧客属性 (例: 建築関係)")
    condition = st.text_input("前提条件 (例: 図面なし)")
    
    if st.button("ヒアリングを開始"):
        if task_name and customer_type and condition:
            st.session_state.context_data = f"業務: {task_name}, 顧客: {customer_type}, 条件: {condition}"
            st.session_state.phase = "interview"
            st.rerun()
        else:
            st.error("全ての項目を入力してください。")

# -------------------------------------------------------------------
# フェーズ2: AIとのヒアリング（壁打ち）
# -------------------------------------------------------------------
elif st.session_state.phase == "interview":
    st.subheader(f"2. ヒアリング実施中: {st.session_state.context_data}")
    
    if st.session_state.chat_session is None:
        init_gemini()
        # 初回のみ、AIに役割と目的を直接指示する
        initial_prompt = f"""
        あなたは製造業の業務プロセスを可視化する優秀なコンサルタントAIです。
        現在の対象業務: {st.session_state.context_data}
        
        【あなたの目的】
        ユーザー（コンサルタント）との対話を通じて、ベテラン社員が頭の中で行っている以下の「暗黙知」を引き出してください。
        1. 判断基準（例：協力工場の選び方など）
        2. 例外処理や分岐
        3. 絶対に外せないリスク確認
        
        【ルール】
        ・一度に複数の質問を詰め込まず、対話形式で1つずつ深掘りしてください。
        ・相手の回答を承認・整理してから、次の質問に進んでください。
        
        それでは、上記を理解した上で、暗黙知を引き出すための「最初のリード質問」を1つだけユーザーに投げかけてください。
        """
        with st.spinner("AIが準備をしています..."):
            response = st.session_state.chat_session.send_message(initial_prompt)
            st.session_state.messages.append({"role": "ai", "content": response.text})

    # これまでの会話履歴を表示
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ユーザーの入力
    user_input = st.chat_input("社長の回答や、深掘りしたい内容を入力してください...")
    
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        with st.chat_message("ai"):
            with st.spinner("AIが質問を考えています..."):
                response = st.session_state.chat_session.send_message(user_input)
                st.markdown(response.text)
                st.session_state.messages.append({"role": "ai", "content": response.text})

    st.markdown("---")
    if st.button("ヒアリングを終了し、プロセス図(UML)を生成する", type="primary"):
        st.session_state.phase = "summary"
        st.rerun()

# -------------------------------------------------------------------
# フェーズ3: ナレッジ構造化とMermaid図の生成
# -------------------------------------------------------------------
elif st.session_state.phase == "summary":
    st.subheader("3. 抽出されたナレッジとプロセス図")
    
    if st.session_state.chat_session is None:
        init_gemini()

    with st.spinner("これまでの対話を構造化し、Mermaidコードを生成しています..."):
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
        
        summary_prompt = f"""
        これまでのヒアリング内容を元に、以下の2点を出力してください。
        
        1. 【構造化データ】: 業務のフロー、判断基準、リスクポイント（外せないポイント）を箇条書きで整理。
        2. 【Mermaidコード】: 上記のプロセスを可視化するMermaid記法のフローチャート（graph TD）コード。
        リスクポイントや重要な判断分岐は、色を変えるなどして強調してください。
        Mermaidコードは必ず ```mermaid と ``` で囲んで出力してください。
        
        ヒアリング履歴：
        {history_text}
        """
        
        final_response = st.session_state.chat_session.send_message(summary_prompt)
        st.markdown(final_response.text)
        
    if st.button("最初からやり直す"):
        st.session_state.clear()
        st.rerun()