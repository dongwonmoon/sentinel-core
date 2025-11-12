import streamlit as st
import requests # FastAPI와 통신하기 위한 라이브러리
import json

# --- 1. 설정 ---
QUERY_API_URL = "http://127.0.0.1:8000/query/corporate" # 우리가 만든 FastAPI 엔드포인트
UPLOAD_API_URL = "http://127.0.0.1:8000/upload-and-index" # [추가] 업로드 API 주소

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
if prompt := st.chat_input("사내 지식에 대해 질문하세요..."):
    # 1. 사용자 메시지 저장 및 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. (핵심) FastAPI 백엔드 '스트리밍' 호출
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        retrieved_chunks = []
        search_result = ""
        tool_choice = ""

        try:
            # 2-1. API 요청 데이터
            payload = {
                "query": prompt,
                "permission_groups": ["all_users"]
            }

            with requests.post(QUERY_API_URL, json=payload, stream=True) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data_json = line_str[len("data: "):]
                            if data_json == "[DONE]": break
                                
                            try:
                                data = json.loads(data_json)
                                if "token" in data:
                                    full_response += data["token"]
                                    message_placeholder.markdown(full_response + "▌")
                                
                                # [수정] 스트림 중간에 오는 '출처' 정보 수신
                                if "chunks" in data and data["chunks"]:
                                    retrieved_chunks = data["chunks"]
                                if "search_result" in data and data["search_result"]:
                                    search_result = data["search_result"]
                                if "tool_choice" in data:
                                    tool_choice = data["tool_choice"]
                                    
                            except json.JSONDecodeError:
                                pass 

            message_placeholder.markdown(full_response)
            
            # [수정] 스트리밍 완료 후 '모든 출처' 표시
            if tool_choice:
                st.info(f"선택된 도구: **{tool_choice}**")
            if retrieved_chunks:
                with st.expander("출처 보기 (RAG)"):
                    st.json(retrieved_chunks)
            if search_result:
                with st.expander("출처 보기 (WebSearch)"):
                    st.text(search_result)

            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except requests.exceptions.RequestException as e:
            st.error(f"백엔드 API 호출에 실패했습니다: {e}")
            st.session_state.messages.append({"role": "assistant", "content": f"API Error: {e}"})