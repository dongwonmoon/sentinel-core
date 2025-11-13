import streamlit as st
import requests
import json
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
GITHUB_API_URL = f"{API_BASE_URL}/index-github-repo"
QUERY_API_URL = f"{API_BASE_URL}/query/corporate"
UPLOAD_API_URL = f"{API_BASE_URL}/upload-and-index"
DOCS_API_URL = f"{API_BASE_URL}/documents"


@st.cache_data(ttl=60)  # 60초마다 갱신
def load_indexed_sources():
    """백엔드에서 현재 인덱싱된 문서 목록을 가져옵니다."""
    try:
        response = requests.get(DOCS_API_URL)
        response.raise_for_status()
        # 예: {"doc-id-123": "hr_policy.txt", "doc-id-456": "my_repo.zip (Zip)"}
        return response.json()
    except Exception as e:
        st.error(f"인덱싱된 문서 목록 로드 실패: {e}")
        return {}


st.set_page_config(page_title="Sentinel-Core", page_icon="🛡️")
st.title("🛡️ Sentinel-Core")
st.caption("Corporate Knowledge Core (RAG)")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "available_sources" not in st.session_state:
    st.session_state.available_sources = load_indexed_sources()
if "selected_contexts" not in st.session_state:
    st.session_state.selected_contexts = list(st.session_state.available_sources.keys())

with st.sidebar:
    st.header("🗂️ 지식 소스 관리")
    st.info("AI와 대화할 컨텍스트(자료)를 관리합니다.")

    with st.expander("➕ 새 지식 소스 추가하기", expanded=False):

        tab1, tab2, tab3 = st.tabs(["📄 개별 파일", "🗂️ 코드 폴더 (.zip)", "🐙 GitHub"])

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
                            data = {"permission_groups_str": json.dumps(["all_users"])}
                            try:
                                response = requests.post(
                                    UPLOAD_API_URL, files=files_data, data=data
                                )
                                response.raise_for_status()
                                st.success(f"'{file.name}' 인덱싱 요청 완료!")
                            except Exception as e:
                                st.error(f"'{file.name}' 업로드 실패: {e}")
                    st.cache_data.clear()
                    st.session_state.available_sources = load_indexed_sources()
                    st.rerun()
        with tab2:
            uploaded_zip = st.file_uploader(
                "코드베이스 .zip 폴더", type=["zip"], key="uploader_zip"
            )
            if st.button("코드 폴더 인덱싱"):
                if uploaded_zip:
                    with st.spinner(
                        f"'{uploaded_zip.name}' 업로드 및 인덱싱 요청 중..."
                    ):
                        files_data = {
                            "file": (
                                uploaded_zip.name,
                                uploaded_zip.getvalue(),
                                uploaded_zip.type,
                            )
                        }
                        data = {"permission_groups_str": json.dumps(["all_users"])}
                        try:
                            response = requests.post(
                                UPLOAD_API_URL, files=files_data, data=data
                            )
                            response.raise_for_status()
                            st.success(f"'{uploaded_zip.name}' 인덱싱 요청 완료!")
                        except Exception as e:
                            st.error(f"'{uploaded_zip.name}' 업로드 실패: {e}")
                    st.cache_data.clear()
                    st.session_state.available_sources = load_indexed_sources()
                    st.rerun()

        with tab3:
            repo_url = st.text_input(
                "GitHub Repo URL (예: https://...)", disabled=False, key="github_url"
            )
            if st.button("GitHub 저장소 인덱싱", disabled=False, key="github_btn"):
                if repo_url:
                    with st.spinner(f"'{repo_url}' 인덱싱 요청 중..."):
                        try:
                            payload = {
                                "repo_url": repo_url,
                                "permission_groups": ["all_users"],
                            }
                            response = requests.post(GITHUB_API_URL, json=payload)
                            response.raise_for_status()

                            response_data = response.json()
                            st.success(f"✅ {response_data.get('message')}")

                            st.cache_data.clear()
                            st.session_state.available_sources = load_indexed_sources()
                            st.rerun()

                        except Exception as e:
                            st.error(f"GitHub 인덱싱 요청 실패: {e}")
                else:
                    st.warning("GitHub URL을 입력해주세요.")

    st.divider()

    st.subheader("🧠 대화 컨텍스트 선택")

    available_sources = st.session_state.available_sources
    if not available_sources:
        st.caption("먼저 지식 소스를 추가해주세요.")
    else:
        selected_options = st.multiselect(
            "대화에 사용할 자료를 선택하세요:",
            options=list(available_sources.keys()),  # ["doc-id-1", "doc-id-2"]
            format_func=lambda x: available_sources.get(x, x),  # "hr_policy.txt"
            default=list(available_sources.keys()),  # 기본값: 모두 선택
        )
        st.session_state.selected_contexts = selected_options

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("선택된 컨텍스트에 대해 질문하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        retrieved_sources = []
        search_result = []
        code_result = None
        tool_choice = ""

        try:
            payload = {
                "query": prompt,
                "permission_groups": ["all_users"],  # MVP
                "top_k": 3,
                "doc_ids_filter": st.session_state.selected_contexts,
            }

            with requests.post(QUERY_API_URL, json=payload, stream=True) as response:
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
            st.error(f"백엔드 API 호출에 실패했습니다: {e}")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"API Error: {e}"}
            )
        except Exception as e:
            st.error(f"예상치 못한 오류가 발생했습니다: {e}")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"Error: {e}"}
            )
