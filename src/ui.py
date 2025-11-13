import streamlit as st
import requests
import json
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
GITHUB_API_URL = f"{API_BASE_URL}/index-github-repo"
QUERY_API_URL = f"{API_BASE_URL}/query/corporate"
UPLOAD_API_URL = f"{API_BASE_URL}/upload-and-index"
DOCS_API_URL = f"{API_BASE_URL}/documents"
TOKEN_API_URL = f"{API_BASE_URL}/token"
REGISTER_API_URL = f"{API_BASE_URL}/register"
CHAT_HISTORY_API_URL = f"{API_BASE_URL}/chat-history"
CHAT_MESSAGE_API_URL = f"{API_BASE_URL}/chat-message"
DELETE_DOCS_API_URL = f"{API_BASE_URL}/documents"


@st.cache_data(ttl=60)  # 60초마다 갱신
def load_indexed_sources(token: str):
    """백엔드에서 현재 인덱싱된 문서 목록을 가져옵니다."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(DOCS_API_URL, headers=headers)
        response.raise_for_status()
        # 예: {"doc-id-123": "hr_policy.txt", "doc-id-456": "my_repo.zip (Zip)"}
        return response.json()
    except Exception as e:
        st.error(f"인덱싱된 문서 목록 로드 실패: {e}")
        return {}


def show_login_page():
    """로그인 및 회원가입 UI를 렌더링합니다."""
    st.title("🛡️ Sentinel-Core")
    st.caption("Corporate Knowledge Core (RAG) - 로그인")

    tab1, tab2 = st.tabs(["🔒 로그인", "👤 회원가입"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("사용자 이름 (Username)")
            password = st.text_input("비밀번호 (Password)", type="password")
            submitted = st.form_submit_button("로그인")

            if submitted:
                if not username or not password:
                    st.error("사용자 이름과 비밀번호를 모두 입력해주세요.")
                else:
                    try:
                        # /token API는 form data (data=...)를 사용합니다
                        response = requests.post(
                            TOKEN_API_URL,
                            data={"username": username, "password": password},
                        )
                        response.raise_for_status()  # 401 등의 오류가 발생하면 예외 발생

                        token_data = response.json()
                        st.session_state["access_token"] = token_data["access_token"]
                        st.session_state["username"] = username
                        st.success("로그인 성공!")
                        st.rerun()  # UI를 새로고침하여 메인 앱으로 전환

                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 401:
                            st.error("사용자 이름 또는 비밀번호가 올바르지 않습니다.")
                        else:
                            st.error(
                                f"로그인 실패: {e.response.json().get('detail', e)}"
                            )
                    except Exception as e:
                        st.error(f"로그인 중 오류 발생: {e}")

    with tab2:
        with st.form("register_form"):
            reg_username = st.text_input("사용자 이름 (Username)", key="reg_user")
            reg_password = st.text_input(
                "비밀번호 (Password)", type="password", key="reg_pass"
            )
            # 사용자 생성 시 권한 그룹 지정 (MVP)
            # (실제 환경에서는 관리자만 지정하거나, LDAP/SSO와 연동해야 함)
            reg_groups = st.multiselect(
                "소속될 권한 그룹 (테스트용)",
                options=["all_users", "dev_team", "hr_team", "legal_team"],
                default=["all_users"],
            )
            reg_submitted = st.form_submit_button("회원가입")

            if reg_submitted:
                if not reg_username or not reg_password or not reg_groups:
                    st.error("모든 필드를 입력해주세요.")
                else:
                    try:
                        # /register API는 JSON (json=...)을 사용합니다
                        payload = {
                            "username": reg_username,
                            "password": reg_password,
                            "permission_groups": reg_groups,
                        }
                        response = requests.post(REGISTER_API_URL, json=payload)
                        response.raise_for_status()  # 400 등의 오류

                        st.success(
                            f"'{reg_username}' 사용자 등록 성공! 이제 로그인 탭에서 로그인하세요."
                        )
                    except requests.exceptions.HTTPError as e:
                        try:
                            detail = e.response.json().get("detail", "알 수 없는 오류")
                        except requests.exceptions.JSONDecodeError:
                            # API가 500 에러와 함께 빈 본문을 보낸 경우
                            detail = f"서버 오류 (HTTP {e.response.status_code})"

                        st.error(f"회원가입 실패: {detail}")

                    except Exception as e:
                        st.error(f"회원가입 중 오류 발생: {e}")


def show_chat_app(token: str, username: str):
    """
    기존 UI 로직을 이 함수 안으로 이동시켰습니다.
    모든 API 호출 시 'token'을 헤더에 포함합니다.
    """

    # API 요청을 위한 공통 헤더
    headers = {"Authorization": f"Bearer {token}"}

    # --- 4-1. 페이지 설정 및 제목 ---
    st.set_page_config(page_title="Sentinel-Core", page_icon="🛡️")

    # 제목 영역에 사용자 정보와 로그아웃 버튼 추가
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.title("🛡️ Sentinel-Core")
        st.caption(f"Logged in as: **{username}**")
    with col2:
        if st.button("Logout", use_container_width=True):
            del st.session_state["access_token"]
            del st.session_state["username"]
            st.cache_data.clear()  # 로그아웃 시 캐시 삭제
            st.rerun()

    # --- 4-2. 세션 상태 초기화 (메인 앱 전용) ---
    if "messages" not in st.session_state:
        # 세션이 비어있으면, DB에서 채팅 기록을 로드합니다.
        try:
            response = requests.get(CHAT_HISTORY_API_URL, headers=headers)
            response.raise_for_status()
            history_data = response.json()
            # Pydantic 모델(ChatMessageHistory)을 딕셔너리 리스트로 변환
            st.session_state.messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in history_data.get("messages", [])
            ]
        except Exception as e:
            st.error(f"채팅 기록 로드 실패: {e}")
            st.session_state.messages = []  # 실패 시 비움

    # available_sources를 토큰을 기반으로 로드
    st.session_state.available_sources = load_indexed_sources(token)

    if "selected_contexts" not in st.session_state:
        st.session_state.selected_contexts = list(
            st.session_state.available_sources.keys()
        )
    else:
        st.session_state.selected_contexts = [
            ctx
            for ctx in st.session_state.selected_contexts
            if ctx in st.session_state.available_sources
        ]

    # --- 4-3. 사이드바: 지식 소스 관리 ---
    with st.sidebar:
        st.header("🗂️ 지식 소스 관리")

        # 4-3-1. 지식 소스 '추가' (Indexing)
        with st.expander("➕ 새 지식 소스 추가하기", expanded=False):
            tab1, tab2, tab3 = st.tabs(
                ["📄 개별 파일", "🗂️ 코드 폴더 (.zip)", "🐙 GitHub"]
            )

            with tab1:
                uploaded_files = st.file_uploader(
                    "PDF, TXT, MD, PY 등 개별 파일",
                    type=[
                        "pdf",
                        "txt",
                        "md",
                        "py",
                        "js",
                        "java",
                        "ts",
                        "go",
                        "c",
                        "cpp",
                        "h",
                    ],
                    accept_multiple_files=True,
                    key="uploader_files",
                )
                if st.button("개별 파일 인덱싱"):
                    if uploaded_files:
                        with st.spinner("파일 업로드 및 인덱싱 요청 중..."):
                            for file in uploaded_files:
                                files_data = {
                                    "file": (file.name, file.getvalue(), file.type)
                                }
                                # data=... 제거 (이제 API가 토큰에서 권한을 읽음)
                                try:
                                    response = requests.post(
                                        UPLOAD_API_URL,
                                        files=files_data,
                                        headers=headers,
                                    )
                                    response.raise_for_status()
                                    st.success(f"'{file.name}' 인덱싱 요청 완료!")
                                except Exception as e:
                                    st.error(f"'{file.name}' 업로드 실패: {e}")
                        # 업로드 후 목록 갱신 (캐시 클리어)
                        st.cache_data.clear()
                        st.session_state.available_sources = load_indexed_sources(token)
                        st.rerun()

            with tab2:
                uploaded_zip = st.file_uploader(
                    "코드베이스 .zip 폴더", type=["zip"], key="uploader_zip"
                )
                if st.button("코드 폴더 인덱싱"):
                    if uploaded_zip:
                        with st.spinner(f"'{uploaded_zip.name}' 업로드 중..."):
                            files_data = {
                                "file": (
                                    uploaded_zip.name,
                                    uploaded_zip.getvalue(),
                                    uploaded_zip.type,
                                )
                            }
                            try:
                                response = requests.post(
                                    UPLOAD_API_URL, files=files_data, headers=headers
                                )
                                response.raise_for_status()
                                st.success(f"'{uploaded_zip.name}' 인덱싱 요청 완료!")
                            except Exception as e:
                                st.error(f"'{uploaded_zip.name}' 업로드 실패: {e}")
                        st.cache_data.clear()
                        st.session_state.available_sources = load_indexed_sources(token)
                        st.rerun()

            with tab3:
                repo_url = st.text_input("GitHub Repo URL", key="github_url")
                if st.button("GitHub 저장소 인덱싱", key="github_btn"):
                    if repo_url:
                        with st.spinner(f"'{repo_url}' 인덱싱 요청 중..."):
                            try:
                                # json=... 페이로드에서 permission_groups 제거
                                payload = {"repo_url": repo_url}
                                response = requests.post(
                                    GITHUB_API_URL, json=payload, headers=headers
                                )
                                response.raise_for_status()
                                st.success(f"'{repo_url}' 인덱싱 요청 완료!")
                            except Exception as e:
                                st.error(f"GitHub 인덱싱 요청 실패: {e}")
                        st.cache_data.clear()
                        st.session_state.available_sources = load_indexed_sources(token)
                        st.rerun()

        st.divider()

        # 4-3-2. 지식 소스 '선택' (Context Filtering)
        st.subheader("🧠 대화 컨텍스트 선택")
        available_sources = st.session_state.available_sources
        if not available_sources:
            st.caption("먼저 지식 소스를 추가해주세요.")
            st.session_state.selected_contexts = []  # 소스가 없으면 선택도 비움
        else:
            # st.multiselect 대신,
            # 각 항목을 순회하며 체크박스와 삭제 버튼을 만듭니다.
            selected_contexts = []

            st.caption("대화에 사용할 자료를 체크하세요.")

            # (UI 정렬을 위해 컨테이너 사용)
            container = st.container(height=250)  # 높이 조절 가능

            for doc_key, display_name in available_sources.items():
                col1, col2 = container.columns([0.85, 0.15])

                # col1: 체크박스 (컨텍스트 선택)
                is_selected = col1.checkbox(
                    display_name,
                    value=(
                        doc_key in st.session_state.selected_contexts
                    ),  # 이전 선택 상태 유지
                    key=f"check_{doc_key}",
                )
                if is_selected:
                    selected_contexts.append(doc_key)

                # col2: 삭제 버튼
                if col2.button(
                    "❌", key=f"del_{doc_key}", help=f"'{display_name}' 삭제"
                ):
                    try:
                        # 삭제 API 호출
                        payload = {"doc_id_or_prefix": doc_key}
                        response = requests.delete(
                            DELETE_DOCS_API_URL, json=payload, headers=headers
                        )
                        response.raise_for_status()

                        st.success(f"'{display_name}' 삭제 완료!")

                        # 목록 갱신을 위해 캐시 클리어 및 재실행
                        st.cache_data.clear()
                        st.session_state.available_sources = load_indexed_sources(token)
                        st.rerun()  # UI를 즉시 새로고침

                    except Exception as e:
                        st.error(f"삭제 실패: {e}")
            st.session_state.selected_contexts = selected_contexts

    # --- 4-4. 메인 채팅 인터페이스 ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("선택된 컨텍스트에 대해 질문하세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            # 사용자 메시지를 DB에 저장
            requests.post(
                CHAT_MESSAGE_API_URL,
                json={"role": "user", "content": prompt},
                headers=headers,
            ).raise_for_status()
        except Exception as e:
            st.error(f"사용자 메시지 저장 실패: {e}")

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            try:
                previous_messages = st.session_state.messages[:-1]

                payload = {
                    "query": prompt,
                    "top_k": 3,
                    "doc_ids_filter": st.session_state.selected_contexts,
                    "chat_history": previous_messages,
                }

                with requests.post(
                    QUERY_API_URL, json=payload, stream=True, headers=headers
                ) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
                        if line:
                            line_str = line.decode("utf-8")
                            if line_str.startswith("data: "):
                                data_json = line_str[len("data: ") :]

                                try:
                                    data = json.loads(data_json)
                                    event_type = data.get("event")

                                    if event_type == "token":
                                        token = data.get("data")
                                        if token:
                                            full_response += token
                                            message_placeholder.markdown(
                                                full_response + "▌"
                                            )

                                    elif event_type == "sources":
                                        sources_data = data.get("data")
                                        if sources_data:
                                            retrieved_sources = sources_data

                                    elif event_type == "tool_choice":
                                        tool_choice = data.get("data")

                                    elif event_type == "search_result":
                                        search_result = data.get("data")

                                    elif event_type == "code_result":
                                        code_result = data.get(
                                            "data"
                                        )  # {'input': ..., 'output': ...}

                                    elif event_type == "end":
                                        break

                                except json.JSONDecodeError:
                                    pass  # 가끔 빈 줄이나 [DONE] 등이 올 수 있음

                message_placeholder.markdown(full_response)  # 최종 답변 고정

                if tool_choice:
                    st.info(f"선택된 도구: **{tool_choice}**")
                if retrieved_sources:
                    with st.expander("출처 보기 (RAG Sources)"):
                        st.json(retrieved_sources)
                if search_result:
                    with st.expander("출처 보기 (WebSearch)"):
                        st.text(search_result)
                if code_result:
                    with st.expander("출처 보기 (Code Execution)"):
                        st.write("**실행된 코드:**")
                        st.code(code_result.get("input", "N/A"), language="python")
                        st.write("**실행 결과:**")
                        st.code(code_result.get("output", "N/A"), language="bash")

                # 세션에 최종 답변 저장
                st.session_state.messages.append(
                    {"role": "assistant", "content": full_response}
                )

            except requests.exceptions.RequestException as e:
                if e.response.status_code == 401:
                    st.error(
                        "인증 토큰이 만료되었습니다. 페이지를 새로고침하여 다시 로그인하세요."
                    )
                    st.session_state["access_token"] = None  # 토큰 만료 시 삭제
                else:
                    st.error(f"백엔드 API 호출에 실패했습니다: {e}")
                full_response = f"API Error: {e}"
            except Exception as e:
                st.error(f"예상치 못한 오류가 발생했습니다: {e}")
                full_response = f"Error: {e}"

            st.session_state.messages.append(
                {"role": "assistant", "content": full_response}
            )

            if "API Error" not in full_response and "Error:" not in full_response:
                try:
                    # AI 메시지를 DB에 저장
                    requests.post(
                        CHAT_MESSAGE_API_URL,
                        json={"role": "assistant", "content": full_response},
                        headers=headers,
                    ).raise_for_status()
                except Exception as e:
                    st.error(f"AI 답변 저장 실패: {e}")


# 세션 상태에 'access_token'이 있는지 확인하여 페이지를 결정
if "access_token" not in st.session_state or st.session_state.access_token is None:
    st.session_state.available_sources = {}  # 로그아웃 시 소스 목록 초기화
    st.session_state.selected_contexts = []
    st.session_state.messages = []
    show_login_page()
else:
    show_chat_app(
        token=st.session_state.access_token,
        username=st.session_state.get("username", "user"),
    )
