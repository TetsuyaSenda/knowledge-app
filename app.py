import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
import re
import html

# =========================
# Page settings
# =========================
st.set_page_config(
    page_title="顧客要求から判断を見える化するアプリ",
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
.small-note {
    font-size: 13px;
    color: #666;
}
.card {
    padding: 16px;
    border-radius: 12px;
    border: 1px solid #E3E8EF;
    background: #FAFBFC;
    margin-bottom: 12px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Session state
# =========================
defaults = {
    "step": 1,
    "messages": [],
    "data": {},
    "current_map": "",
    "current_knowledge": "",
    "final_document": "",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================
# Mermaid utilities
# =========================
def extract_mermaid_code(raw_text: str) -> str:
    """Extract Mermaid code from markdown block or raw Mermaid-like text."""
    code_text = raw_text or ""

    match = re.search(r"```mermaid(.*?)```", code_text, re.DOTALL)
    if match:
        code_text = match.group(1).strip()
    else:
        code_text = code_text.replace("```", "").strip()

    # Remove accidental section markers or markdown headings that break Mermaid.
    cleanup_lines = []
    for line in code_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("==="):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            continue
        cleanup_lines.append(stripped)

    code_text = "\n".join(cleanup_lines).strip()

    # Ensure Mermaid graph header exists.
    if code_text and not re.match(r"^(graph|flowchart)\s+", code_text):
        code_text = "flowchart TD\n" + code_text

    # Prefer flowchart TD for Mermaid 10.
    code_text = re.sub(r"^graph\s+TD", "flowchart TD", code_text, flags=re.MULTILINE)

    return code_text


def default_mermaid() -> str:
    return """flowchart TD
A["顧客要求"] --> B{"最初に確認すること"}
B --> C{"制約・リスク"}
C --> D{"トレードオフ"}
D --> E["判断・対応方針"]
"""


def render_mermaid(mermaid_code: str) -> None:
    code_text = extract_mermaid_code(mermaid_code)

    if not code_text:
        code_text = default_mermaid()

    # Escape for JS template literal safety.
    safe_code = code_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    visible_code = html.escape(code_text)

    html_code = f"""
    <div id="mermaid-container" style="width:100%; overflow:auto; padding:8px;">
      <pre class="mermaid">{safe_code}</pre>
    </div>

    <details style="margin-top:10px;">
      <summary style="cursor:pointer; color:#666;">Mermaidコードを表示</summary>
      <pre style="white-space:pre-wrap; font-size:12px; background:#f7f7f7; padding:8px; border-radius:8px;">{visible_code}</pre>
    </details>

    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{
        startOnLoad: false,
        theme: 'default',
        securityLevel: 'loose'
      }});

      const el = document.querySelector('#mermaid-container .mermaid');
      try {{
        await mermaid.run({{ nodes: [el] }});
      }} catch (e) {{
        el.innerHTML = '<div style="color:#b00020; padding:12px; border:1px solid #f0b8b8; border-radius:8px; background:#fff5f5;">図の描画に失敗しました。抽出ナレッジは右タブで確認できます。<br><small>' + e.message + '</small></div>';
      }}
    </script>
    """

    components.html(html_code, height=680, scrolling=True)


# =========================
# Sidebar and AI call
# =========================
st.sidebar.title("設定")
api_key = st.sidebar.text_input("Gemini APIキーを入力", type="password")
st.sidebar.markdown("---")
st.sidebar.caption("第1段階：顧客要求を起点に、ベテランの判断構造を可視化するアプリです。")


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

    # Harden map text against partial/invalid output.
    map_text = extract_mermaid_code(map_text)
    if not map_text:
        map_text = default_mermaid()

    return chat_text.strip(), map_text.strip(), knowledge_text.strip()


# =========================
# Prompt builders
# =========================
def build_system_prompt() -> str:
    company_info = st.session_state.data.get("company_info", "")
    industry = st.session_state.data.get("industry", "")
    customer_request = st.session_state.data.get("customer_request", "")
    request_detail = st.session_state.data.get("request_detail", "")
    focus_area = st.session_state.data.get("focus_area", "")

    return f"""
あなたは、少人数製造業の「顧客要求に対する意思決定構造」を可視化する専門コンサルタントです。

目的は、単なる業務手順やマニュアルを作ることではありません。
顧客要求を受けた時に、ベテラン社員や経営者が
「何を危険と見て」
「どの制約を確認し」
「何と何をトレードオフとして考え」
「最終的にどのように判断するのか」
を引き出し、若手社員や現場担当者が再現できる判断ナレッジに変換することです。

対象企業情報:
{company_info}

業種:
{industry}

顧客要求テーマ:
{customer_request}

顧客要求の具体例:
{request_detail}

重点的に見たい領域:
{focus_area}

特に重視する観点:
1. 顧客要求の内容
2. 顧客が本当に求めている価値
3. 最初に確認すべき情報
4. 発生しやすい問題
5. 制約条件
6. トレードオフ
7. 見積への影響
8. 工程設計への影響
9. 協力工場選定への影響
10. 品質判断への影響
11. 優先順位
12. 危険シグナル
13. 上長確認が必要なライン
14. ベテラン特有の着眼点
15. 例外対応
16. 若手が間違えやすいポイント
17. 次に蓄積すべきデータ

質問ルール:
- 1回につき質問は1つだけ
- 「顧客要求」を起点に質問する
- 相手が答えやすいように、製造業の具体例を交える
- 抽象的に聞きすぎない
- 「なぜそう判断するのか」を必ず深掘りする
- 見積、工程設計、協力工場選定、品質判断のどこに影響するかを意識する
- まだ情報が足りない場合は、無理に結論を出さず「未確認事項」として残す
- AIが最終判断するのではなく、人が判断するための材料を整理する前提で進める

Mermaid作成ルール:
- 必ず flowchart TD で始める
- ノードの文字は必ず ["..."] または {{"..."}} で囲む
- ノードIDは A, B, C1, C2 のように半角英数字だけにする
- 丸括弧 () は使わない
- コロン :、セミコロン ;、スラッシュ /、バックスラッシュ、引用符はノード文言に使わない
- 矢印ラベルは |はい| |いいえ| |高い| |低い| のように短くする
- Mermaidブロック内には説明文や箇条書きを入れない

出力は必ず以下の形式にしてください。

===CHAT===
相手への短い相槌と、次の深掘り質問を1つだけ書く。

===MAP===
```mermaid
flowchart TD
A["顧客要求"] --> B{{"最初の確認"}}
B --> C{{"制約とリスク"}}
C --> D{{"トレードオフ"}}
D --> E["判断と対応方針"]
```

===KNOWLEDGE===
## 顧客要求
- 

## 顧客が本当に求めている価値
- 

## 発生しやすい問題
- 

## 制約条件
- 

## トレードオフ
- 

## 見積への影響
- 

## 工程設計への影響
- 

## 協力工場選定への影響
- 

## 品質判断への影響
- 

## 判断ポイント
- 

## 危険シグナル
- 

## 優先順位
- 

## 上長確認が必要なライン
- 

## ベテラン特有の着眼点
- 

## 若手が間違えやすいポイント
- 

## 未確認事項
- 
"""


def build_final_prompt() -> str:
    customer_request = st.session_state.data.get("customer_request", "顧客要求")
    request_detail = st.session_state.data.get("request_detail", "")
    focus_area = st.session_state.data.get("focus_area", "")
    history = st.session_state.messages
    current_map = st.session_state.current_map
    current_knowledge = st.session_state.current_knowledge

    return f"""
以下は、顧客要求起点の暗黙知抽出ヒアリングの会話履歴と、途中で抽出された判断マップ・判断ナレッジです。
これらをもとに、NotebookLMや社内チャットボットに読み込ませやすい
「顧客要求別・判断ナレッジ用マスタードキュメント」を作成してください。

顧客要求テーマ:
{customer_request}

顧客要求の具体例:
{request_detail}

重点的に見たい領域:
{focus_area}

会話履歴:
{history}

現在の判断マップ:
{current_map}

現在の判断ナレッジ:
{current_knowledge}

出力形式:

# {customer_request} 顧客要求別・判断ナレッジ マスタードキュメント

## 1. 顧客要求の概要

## 2. 顧客が本当に求めている価値

## 3. 最初に確認すべき情報

## 4. 発生しやすい問題パターン

## 5. 制約条件

## 6. トレードオフ

## 7. 見積への影響

## 8. 工程設計への影響

## 9. 協力工場選定への影響

## 10. 品質判断への影響

## 11. 判断ポイント一覧

## 12. 危険シグナル

## 13. ケース別の推奨対応

## 14. 上長確認が必要なライン

## 15. ベテラン特有の着眼点

## 16. 若手が間違えやすいポイント

## 17. 未確認事項・今後ヒアリングすべきこと

## 18. AIチャットボット化する際に必要なデータ

## 19. 新人向けの簡易マニュアル
"""


# =========================
# Header
# =========================
col_logo, col_title = st.columns([1, 8])

with col_logo:
    st.image(
        "https://organa.jp/images/logomark.svg",
        width=80,
    )

with col_title:
    st.title("顧客要求から判断を見える化")
    st.caption("顧客の要望に対して、見積・工程・協力工場・品質の判断構造を整理するアプリ")

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
    st.subheader("Step 3：今回整理したい顧客要求を選んでください")

    customer_request = st.radio(
        "顧客要求テーマ",
        [
            "短納期要求",
            "高精度要求",
            "低コスト要求",
            "図面なし案件",
            "試作対応",
            "品質優先",
            "大量ロット",
            "仕様変更",
            "クレーム・不具合対応",
            "その他",
        ],
    )

    request_detail = st.text_area(
        "顧客要求の具体例",
        height=100,
        placeholder=(
            "例：お客様から『通常より早く納品してほしい』と言われた。"
            "その場合、見積・工程設計・協力工場選定・品質判断にどのような影響が出るかを整理したい。"
        ),
    )

    focus_area = st.multiselect(
        "重点的に見たい領域",
        [
            "見積",
            "工程設計",
            "協力工場選定",
            "品質判断",
            "納期調整",
            "顧客対応",
            "社内優先順位",
        ],
        default=["見積", "工程設計", "協力工場選定", "品質判断"],
    )

    st.info(
        "おすすめデモテーマ：『短納期要求』。"
        "見積・工程設計・協力工場選定・品質判断に横断的な影響が出やすく、"
        "顧客要求起点の意思決定構造を見せやすいテーマです。"
    )

    if st.button("ヒアリングを開始する", type="primary"):
        if request_detail:
            st.session_state.data["customer_request"] = customer_request
            st.session_state.data["request_detail"] = request_detail
            st.session_state.data["focus_area"] = "、".join(focus_area)
            st.session_state.step = 4
            st.rerun()
        else:
            st.warning("顧客要求の具体例を入力してください。")


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
                        "顧客要求を起点に、最初の深掘り質問をしてください。初期の判断マップと判断ナレッジも出力してください。",
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
以下の会話履歴を踏まえて、顧客要求に対する意思決定構造をさらに深掘りする質問を1つ行ってください。
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
                    "あなたは製造業の顧客要求起点の暗黙知を、AIナレッジベース用ドキュメントへ整理する専門家です。",
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
                st.caption("ヒアリングを進めると、顧客要求・問題・制約・トレードオフ・判断ポイントがここに整理されます。")


# =========================
# Step 5: Final output
# =========================
elif st.session_state.step == 5:
    st.subheader("顧客要求別・判断ナレッジ生成完了")

    st.success(
        "ヒアリング内容から、判断支援AIやNotebookLMに読み込ませやすいマスタードキュメントを生成しました。"
    )

    col1, col2 = st.columns([0.9, 1.4])

    with col1:
        st.markdown("### 生成された成果物")
        st.write("1. 顧客要求別の判断フローチャート")
        st.write("2. 発生しやすい問題パターン")
        st.write("3. 制約条件・トレードオフ")
        st.write("4. 見積・工程・工場選定・品質への影響")
        st.write("5. AIナレッジ用ドキュメント")

        st.markdown("---")

        st.download_button(
            label="マスタードキュメントをダウンロード",
            data=st.session_state.final_document,
            file_name=f"{st.session_state.data.get('customer_request', '顧客要求')}_master_document.md",
            mime="text/markdown",
            use_container_width=True,
        )

        if st.button("新しい顧客要求を登録する", use_container_width=True):
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
