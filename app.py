import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
import re

# =========================
# Page settings
# =========================
st.set_page_config(
    page_title="ベテランの経験や勘を見える化するアプリ",
    layout="wide"
)

# =========================
# Styles
# =========================
st.markdown(
    """
<style>
.footer {
    text-align: center;
    color: gray;
    font-size: 12px;
    padding-top: 50px;
    padding-bottom: 20px;
}
.block-title {
    font-size: 18px;
    font-weight: bold;
    margin-top: 10px;
}
.small-note {
    font-size: 13px;
    color: #666;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Session state
# =========================
if "step" not in st.session_state:
    st.session_state.step = 1

if "messages" not in st.session_state:
    st.session_state.messages = []

if "data" not in st.session_state:
    st.session_state.data = {}

if "current_map" not in st.session_state:
    st.session_state.current_map = ""

if "current_knowledge" not in st.session_state:
    st.session_state.current_knowledge = ""

if "final_document" not in st.session_state:
    st.session_state.final_document = ""


# =========================
# Mermaid renderer
# =========================
def render_mermaid(mermaid_code: str) -> None:
    code_text = mermaid_code or ""

    match = re.search(r"```mermaid(.*?)```", code_text, re.DOTALL)
    if match:
        code_text = match.group(1).strip()

    code_text = code_text.replace("```", "").strip()

    if not code_text:
        st.caption("判断マップはまだ生成されていません。")
        return

    html_code = f"""
    <div class="mermaid" style="display:flex; justify-content:center; font-family:sans-serif;">
        {code_text}
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_code, height=620, scrolling=True)


# =========================
# Sidebar and AI call
# =========================
st.sidebar.title("設定")
api_key = st.sidebar.text_input("Gemini APIキーを入力", type="password")

st.sidebar.markdown("---")
st.sidebar.caption("本アプリは第1段階：暗黙知の可視化・判断軸抽出用です。")


def get_ai_response(prompt: str, system_prompt: str = "") -> str | None:
    if not api_key:
        st.error("左側のサイドバーからGemini APIキーを入力してください。")
        return None

    genai.configure(api_key=api_key)

    try:
        models = [
            m.name
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]

        if "models/gemini-1.5-flash" in models:
            model_name = "gemini-1.5-flash"
        elif "models/gemini-1.5-pro" in models:
            model_name = "gemini-1.5-pro"
        else:
            model_name = models[0]

        model = genai.GenerativeModel(
            model_name,
            system_instruction=system_prompt,
        )

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "Quota" in error_msg:
            st.error("AIの利用枠の上限に達しました。時間を置いて再実行してください。")
        else:
            st.error(f"エラーが発生しました: {error_msg}")
        return None


# =========================
# Parse AI response
# =========================
def parse_ai_response(response_text: str) -> tuple[str, str, str]:
    chat_text = response_text or ""
    map_text = st.session_state.current_map
    knowledge_text = st.session_state.current_knowledge

    if not response_text:
        return "", map_text, knowledge_text

    if "===CHAT===" in response_text:
        chat_part = response_text.split("===CHAT===", 1)[1]

        if "===MAP===" in chat_part:
            chat_text = chat_part.split("===MAP===", 1)[0].strip()
            rest = chat_part.split("===MAP===", 1)[1]

            if "===KNOWLEDGE===" in rest:
                map_text = rest.split("===KNOWLEDGE===", 1)[0].strip()
                knowledge_text = rest.split("===KNOWLEDGE===", 1)[1].strip()
            else:
                map_text = rest.strip()
        else:
            chat_text = chat_part.strip()

    return chat_text.strip(), map_text.strip(), knowledge_text.strip()


# =========================
# Prompt builders
# =========================
def build_system_prompt() -> str:
    company_info = st.session_state.data.get("company_info", "")
    industry = st.session_state.data.get("industry", "")
    task_category = st.session_state.data.get("task_category", "")
    task_name = st.session_state.data.get("task_name", "")

    return f"""
あなたは、少人数製造業の暗黙知を可視化し、ベテラン社員の判断軸を抽出する専門コンサルタントです。

目的は、単なる業務手順を聞き出すことではありません。
ベテラン社員が「どの条件で」「なぜその判断をするのか」を引き出し、
若手社員や現場担当者が再現できる判断ナレッジに変換することです。

対象企業情報:
{company_info}

業種:
{industry}

対象業務カテゴリ:
{task_category}

対象業務:
{task_name}

特に重視する観点:
1. 最初に確認する情報
2. 判断が分かれる条件
3. 危険なパターン
4. 過去類似案件を見る基準
5. 若手が間違えやすいポイント
6. 社長・工場長・責任者に確認すべきライン
7. 判断理由
8. 例外対応
9. 失敗事例
10. 次に蓄積すべき情報

質問ルール:
- 1回につき質問は1つだけ
- 相手が答えやすいように、製造業の具体例を交える
- 抽象的に聞きすぎない
- 「なぜそう判断するのか」を必ず深掘りする
- 手順だけでなく、判断軸・分岐条件・リスクを抽出する
- まだ情報が足りない場合は、無理に結論を出さず「未確認事項」として残す

出力は必ず以下の形式にしてください。

===CHAT===
相手への短い相槌と、次の深掘り質問を1つだけ書く。

===MAP===
```mermaid
graph TD
A[対象業務] --> B{{判断条件}}
B -->|条件A| C[対応A]
B -->|条件B| D[対応B]
```

===KNOWLEDGE===
## 判断軸
- 

## 確認事項
- 

## 分岐条件
- 

## 推奨対応
- 

## 注意点・リスク
- 

## 若手が間違えやすいポイント
- 

## 上長確認が必要なライン
- 

## 未確認事項
- 
"""


def build_final_prompt() -> str:
    task_name = st.session_state.data.get("task_name", "判断テーマ")
    history = st.session_state.messages
    current_map = st.session_state.current_map
    current_knowledge = st.session_state.current_knowledge

    return f"""
以下は、暗黙知抽出ヒアリングの会話履歴と、途中で抽出された判断マップ・判断ナレッジです。
これらをもとに、NotebookLMや社内チャットボットに読み込ませやすい
「AIナレッジ用マスタードキュメント」を作成してください。

対象業務:
{task_name}

会話履歴:
{history}

現在の判断マップ:
{current_map}

現在の判断ナレッジ:
{current_knowledge}

出力形式:

# {task_name} 判断ナレッジ・マスタードキュメント

## 1. 対象業務の概要

## 2. 業務の目的

## 3. 最初に確認すべき情報

## 4. 判断軸一覧

## 5. 判断分岐フロー

## 6. ケース別の推奨対応

## 7. 注意点・リスク

## 8. 若手が間違えやすいポイント

## 9. 上長確認が必要なライン

## 10. 未確認事項・今後ヒアリングすべきこと

## 11. AIチャットボット化する際に必要なデータ

## 12. 新人向けの簡易マニュアル
"""


# =========================
# Header
# =========================
col_logo, col_title = st.columns([1, 8])

with col_logo:
    st.image(
        "https://organa.jp/images/logomark.svg",
        width=80  # ←サイズ調整ここ
    )

with col_title:
    st.title("ベテランの経験や勘を見える化")
    st.caption("ベテランの判断を、若手が使える知識に変える暗黙知可視化アプリ")
st.markdown("---")


# =========================
# Step 1 to 3
# =========================
if st.session_state.step < 4:
    progress_pct = (st.session_state.step - 1) * 33
    st.progress(progress_pct)


if st.session_state.step == 1:
    st.subheader("Step 1：会社・事業について教えてください")

    st.write(
        "対象企業の事業内容や特徴を入力してください。"
        "WebサイトURL、会社概要、取引先の特徴、製造品目など、分かる範囲で構いません。"
    )

    company_input = st.text_area(
        "会社情報",
        height=140,
        placeholder=(
            "例：金属部品の製造業。少量多品種で、顧客ごとの個別対応が多い。"
            "協力工場も多く、見積・工程設計・工場選定に経験が必要。"
        ),
    )

    if st.button("次へ進む", type="primary"):
        st.session_state.data["company_info"] = company_input
        st.session_state.step = 2
        st.rerun()


elif st.session_state.step == 2:
    st.subheader("Step 2：業種を選択してください")

    industry = st.selectbox(
        "該当するカテゴリーを選んでください",
        [
            "製造業",
            "建設・不動産",
            "IT・情報通信",
            "卸売・小売",
            "医療・福祉",
            "サービス業",
            "その他",
        ],
    )

    if st.button("決定して次へ", type="primary"):
        st.session_state.data["industry"] = industry
        st.session_state.step = 3
        st.rerun()


elif st.session_state.step == 3:
    st.subheader("Step 3：今回抽出したい判断テーマを選んでください")

    task_category = st.radio(
        "判断テーマ",
        [
            "新規見積",
            "図面なし案件対応",
            "工程設計",
            "協力工場選定",
            "品質判断",
            "納期調整",
            "クレーム・不具合対応",
            "その他",
        ],
    )

    task_name = st.text_input(
        "具体的な業務名",
        placeholder="例：図面なしの新規見積判断、協力工場の選定判断、NC旋盤の工程設計判断",
    )

    st.info(
        "おすすめデモテーマ：『図面なしの新規見積判断』。"
        "判断軸・リスク・確認事項が出やすく、製造業の暗黙知を可視化しやすいテーマです。"
    )

    if st.button("ヒアリングを開始する", type="primary"):
        if task_name:
            st.session_state.data["task_category"] = task_category
            st.session_state.data["task_name"] = task_name
            st.session_state.step = 4
            st.rerun()
        else:
            st.warning("具体的な業務名を入力してください。")


# =========================
# Step 4: Interview
# =========================
elif st.session_state.step == 4:
    col_chat, col_map = st.columns([1, 1.25])
    system_prompt = build_system_prompt()

    with col_chat:
        st.subheader("AIヒアリング")
        st.info("音声入力を使う場合：Windowsは Win + H / Macは fnキー2回 が便利です。")

        chat_container = st.container(height=560)

        with chat_container:
            if not st.session_state.messages:
                with st.spinner("AIが最初の質問を準備しています..."):
                    initial_response = get_ai_response(
                        "対象業務について、最初の質問をしてください。初期の判断マップと判断ナレッジも出力してください。",
                        system_prompt,
                    )

                    if initial_response:
                        chat_text, map_text, knowledge_text = parse_ai_response(initial_response)

                        st.session_state.current_map = map_text
                        st.session_state.current_knowledge = knowledge_text
                        st.session_state.messages.append(
                            {"role": "assistant", "content": chat_text}
                        )

                    st.rerun()

            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        user_input = st.chat_input("回答を入力してください...")

        if user_input:
            st.session_state.messages.append(
                {"role": "user", "content": user_input}
            )

            history_text = str(st.session_state.messages[-8:])

            prompt = f"""
以下の会話履歴を踏まえて、次の深掘り質問を1つ行ってください。
同時に、判断マップと判断ナレッジを更新してください。

会話履歴:
{history_text}

現在の判断マップ:
{st.session_state.current_map}

現在の判断ナレッジ:
{st.session_state.current_knowledge}
"""

            with st.spinner("回答を分析し、判断マップを更新中..."):
                response = get_ai_response(prompt, system_prompt)

                if response:
                    chat_text, map_text, knowledge_text = parse_ai_response(response)

                    st.session_state.current_map = map_text
                    st.session_state.current_knowledge = knowledge_text
                    st.session_state.messages.append(
                        {"role": "assistant", "content": chat_text}
                    )

                st.rerun()

    with col_map:
        st.subheader("現在の判断マップ")

        if st.button(
            "ヒアリング完了：マスタードキュメント生成へ",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("AIナレッジ用マスタードキュメントを生成しています..."):
                final_response = get_ai_response(
                    build_final_prompt(),
                    "あなたは製造業の暗黙知を、AIナレッジベース用ドキュメントへ整理する専門家です。",
                )

                if final_response:
                    st.session_state.final_document = final_response
                    st.session_state.step = 5
                    st.rerun()

        st.markdown("---")

        tab1, tab2 = st.tabs(["判断マップ", "抽出ナレッジ"])

        with tab1:
            render_mermaid(st.session_state.current_map)

        with tab2:
            if st.session_state.current_knowledge:
                st.markdown(st.session_state.current_knowledge)
            else:
                st.caption("ヒアリングを進めると、判断軸・注意点・未確認事項がここに整理されます。")


# =========================
# Step 5: Final output
# =========================
elif st.session_state.step == 5:
    st.subheader("判断ナレッジ・マスタードキュメント生成完了")

    st.success(
        "ヒアリング内容から、判断支援AIやNotebookLMに読み込ませやすいマスタードキュメントを生成しました。"
    )

    col1, col2 = st.columns([0.9, 1.4])

    with col1:
        st.markdown("### 生成された成果物")
        st.write("1. 判断フローチャート")
        st.write("2. 判断軸一覧")
        st.write("3. ケース別対応")
        st.write("4. 注意点・リスク")
        st.write("5. AIナレッジ用ドキュメント")

        st.markdown("---")

        st.download_button(
            label="マスタードキュメントをダウンロード",
            data=st.session_state.final_document,
            file_name=f"{st.session_state.data.get('task_name', '判断ナレッジ')}_master_document.md",
            mime="text/markdown",
            use_container_width=True,
        )

        if st.button("新しい判断テーマを登録する", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    with col2:
        st.markdown("### AIナレッジ用マスタードキュメント")
        st.markdown(st.session_state.final_document)

        st.markdown("---")
        st.markdown("### 最終判断マップ")
        render_mermaid(st.session_state.current_map)


# =========================
# Footer
# =========================
st.markdown(
    '<div class="footer">Copyright &copy; ORGANA Co., Ltd.</div>',
    unsafe_allow_html=True,
)
