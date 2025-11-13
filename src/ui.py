import streamlit as st
import requests
import json
import os


# --- 1. 설정 ---
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

QUERY_API_URL = f"{API_BASE_URL}/query/corporate"
UPLOAD_API_URL = f"{API_BASE_URL}/upload-and-index"

# --- 2. 페이지 설정 및 제목 ---
st.set_page_config(page_title="Sentinel-Core", page_icon="🛡️")
st.title("🛡️ Sentinel-Core")
st.caption("Corporate Knowledge Core (RAG)")

with st.sidebar:
    st.header("Upload Document (Async)")
    st.info("파일을 업로드하면 백그라운드에서 자동 인덱싱됩니다.")
    
    uploaded_file = st.file_uploader("Upload PDF, TXT, or MD", type=["pdf", "txt", "md"])
    
    # MVP: 모든 파일은 'all_users' 권한으로 업로드
    permission_groups = ["all_users"] 
    
    if st.button("Index File"):
        if uploaded_file is not None:
            with st.spinner("Uploading..."):
                try:
                    # 1. 파일 데이터 준비 (multipart/form-data)
                    files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    
                    # 2. Form 데이터 준비
                    data = {'permission_groups_str': json.dumps(permission_groups)}
                    
                    # 3. API 호출
                    response = requests.post(UPLOAD_API_URL, files=files, data=data)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    st.success(f"✅ {response_data.get('message')}")
                
                except requests.exceptions.RequestException as e:
                    st.error(f"API Error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("먼저 파일을 업로드해주세요.")

# --- 3. 세션 상태 초기화 (채팅 기록용) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 5. 사용자 입력 처리 (채팅 입력창) ---
if prompt := st.chat_input("사내/외부 지식에 대해 질문하세요..."):
    # 1. 사용자 메시지 저장 및 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. (핵심) FastAPI 백엔드 '스트리밍' 호출
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        retrieved_sources = []
        search_result = []
        code_result = None
        tool_choice = ""

        try:
            # 2-1. API 요청 데이터 (main.py의 QueryRequest와 일치)
            payload = {
                "query": prompt,
                "permission_groups": ["all_users"],
                "top_k": 3 # config.py의 기본값과 일치
            }

            # [수정] stream=True로 API 호출
            with requests.post(QUERY_API_URL, json=payload, stream=True) as response:
                response.raise_for_status()
                
                # [수정] main.py의 event 기반 SSE 파싱
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data_json = line_str[len("data: "):]
                            
                            try:
                                data = json.loads(data_json)
                                event_type = data.get("event")

                                if event_type == "token":
                                    token = data.get("data")
                                    if token:
                                        full_response += token
                                        message_placeholder.markdown(full_response + "▌")
                                
                                elif event_type == "sources":
                                    sources_data = data.get("data")
                                    if sources_data:
                                        retrieved_sources = sources_data
                                        
                                elif event_type == "tool_choice":
                                    tool_choice = data.get("data")
                                
                                elif event_type == "search_result":
                                    search_result = data.get("data")

                                elif event_type == "code_result":
                                    code_result = data.get("data") # {'input': ..., 'output': ...}
                                
                                elif event_type == "end":
                                    break
                                    
                            except json.JSONDecodeError:
                                pass # 가끔 빈 줄이나 [DONE] 등이 올 수 있음

            message_placeholder.markdown(full_response) # 최종 답변 고정
            
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
                    st.code(code_result.get('input', 'N/A'), language="python")
                    st.write("**실행 결과:**")
                    st.code(code_result.get('output', 'N/A'), language="bash")
                    
            # 세션에 최종 답변 저장
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except requests.exceptions.RequestException as e:
            st.error(f"백엔드 API 호출에 실패했습니다: {e}")
            st.session_state.messages.append({"role": "assistant", "content": f"API Error: {e}"})
        except Exception as e:
            st.error(f"예상치 못한 오류가 발생했습니다: {e}")
            st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})