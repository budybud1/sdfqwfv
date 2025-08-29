import streamlit as st
import json
from notion_client import Client
import pandas as pd
import re
from typing import Dict, List, Any
import time

# 페이지 설정
st.set_page_config(
    page_title="JSON to Notion 업로더",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .error-box {
        padding: 1rem;
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .info-box {
        padding: 1rem;
        background-color: #d1ecf1;
        border-left: 5px solid #17a2b8;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .stButton > button {
        width: 100%;
        border-radius: 5px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }
    
    .upload-section {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        border: 2px dashed #dee2e6;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class NotionUploader:
    def __init__(self, token: str, database_id: str):
        self.notion = Client(auth=token)
        self.database_id = database_id
        self.db_info = None
    
    def test_connection(self):
        """Notion 연결 테스트"""
        try:
            self.db_info = self.notion.databases.retrieve(database_id=self.database_id)
            return True, "연결 성공!"
        except Exception as e:
            return False, f"연결 실패: {str(e)}"
    
    def get_database_properties(self):
        """데이터베이스 속성 정보 가져오기"""
        if not self.db_info:
            return {}
        
        properties = {}
        for prop_name, prop_info in self.db_info['properties'].items():
            properties[prop_name] = prop_info['type']
        return properties
    
    def upload_person(self, person_data: Dict[str, Any]) -> tuple[bool, str]:
        """단일 인물 데이터 업로드"""
        try:
            if not person_data.get("이름"):
                return False, "이름이 없는 데이터입니다."
            
            properties = self._build_properties(person_data)
            
            self.notion.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            
            return True, f"'{person_data['이름']}' 업로드 완료"
            
        except Exception as e:
            return False, f"업로드 실패: {str(e)}"
    
    def _build_properties(self, person_data: Dict[str, Any]) -> Dict[str, Any]:
        """Notion 속성 구성"""
        properties = {}
        
        # 이름 (Title)
        properties["이름"] = {
            "title": [{"text": {"content": str(person_data["이름"])}}]
        }
        
        # 이메일
        if person_data.get("이메일"):
            properties["이메일"] = {"email": person_data["이메일"]}
        
        # 전화번호
        if person_data.get("전화번호"):
            phone = self._format_phone(person_data["전화번호"])
            try:
                properties["전화번호"] = {"phone_number": phone}
            except:
                properties["전화번호"] = {"rich_text": [{"text": {"content": phone}}]}
        
        # Select 필드들
        select_fields = {
            "나이/탄생연도": person_data.get("나이(탄생연도)") or person_data.get("나이/탄생연도"),
            "성별": person_data.get("성별"),
        }
        
        for field, value in select_fields.items():
            if value and field in self.db_info['properties']:
                if self.db_info['properties'][field]['type'] == 'select':
                    properties[field] = {"select": {"name": str(value)}}
        
        # Rich Text 필드들
        rich_text_fields = {
            "총경력": person_data.get("총경력"),
            "최종학력(전공)": person_data.get("최종학력(학교-전공)") or person_data.get("최종학력(전공)"),
            "최종직장": person_data.get("최종직장"),
            "직급/주요업무": person_data.get("직급/주요업무"),
            "핵심역량": person_data.get("핵심역량"),
            "포지션": person_data.get("포지션"),
        }
        
        for field, value in rich_text_fields.items():
            if value and field in self.db_info['properties']:
                prop_type = self.db_info['properties'][field]['type']
                if prop_type == 'rich_text':
                    properties[field] = {"rich_text": [{"text": {"content": str(value)}}]}
                elif prop_type == 'multi_select' and field == "포지션":
                    values = [v.strip() for v in str(value).split(',')]
                    properties[field] = {"multi_select": [{"name": val} for val in values if val]}
        
        return properties
    
    def _format_phone(self, phone: str) -> str:
        """전화번호 형식 정리"""
        phone_cleaned = ''.join(filter(str.isdigit, str(phone)))
        
        if len(phone_cleaned) == 11 and phone_cleaned.startswith('010'):
            return f"{phone_cleaned[:3]}-{phone_cleaned[3:7]}-{phone_cleaned[7:]}"
        
        return str(phone)

def main():
    # 헤더
    st.markdown("""
    <div class="main-header">
        <h1>📝 JSON to Notion 업로더</h1>
        <p>JSON 데이터를 Notion 데이터베이스에 쉽게 업로드하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 사이드바 - 설정
    with st.sidebar:
        st.header("⚙️ Notion 설정")
        
        notion_token = st.text_input(
            "Notion Integration Token",
            type="password",
            value=st.session_state.get('notion_token', ''),
            help="Notion Integration에서 생성한 토큰을 입력하세요."
        )
        
        database_id = st.text_input(
            "Database ID",
            value=st.session_state.get('database_id', ''),
            help="Notion 데이터베이스 ID를 입력하세요."
        )
        
        # 설정 저장
        if notion_token:
            st.session_state['notion_token'] = notion_token
        if database_id:
            st.session_state['database_id'] = database_id
        
        # 연결 테스트
        if st.button("🔍 연결 테스트"):
            if not notion_token or not database_id:
                st.error("Token과 Database ID를 모두 입력해주세요.")
            else:
                with st.spinner("연결 테스트 중..."):
                    uploader = NotionUploader(notion_token, database_id)
                    success, message = uploader.test_connection()
                    
                    if success:
                        st.success(message)
                        st.session_state['connection_verified'] = True
                        st.session_state['uploader'] = uploader
                        
                        # 데이터베이스 속성 표시
                        properties = uploader.get_database_properties()
                        st.subheader("📋 데이터베이스 속성")
                        for prop_name, prop_type in properties.items():
                            if prop_name in ['이름', '이메일', '전화번호', '총경력', '나이/탄생연도', '성별', '최종학력(전공)', '핵심역량', '포지션', '최종직장', '직급/주요업무']:
                                st.text(f"• {prop_name}: {prop_type}")
                    else:
                        st.error(message)
                        st.session_state['connection_verified'] = False
    
    # 메인 콘텐츠
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📥 데이터 입력")
        
        # 입력 방법 선택
        input_method = st.radio(
            "입력 방법을 선택하세요:",
            ["📁 JSON 파일 업로드", "✏️ JSON 텍스트 입력"],
            horizontal=True
        )
        
        data = None
        
        if input_method == "📁 JSON 파일 업로드":
            st.markdown('<div class="upload-section">', unsafe_allow_html=True)
            uploaded_file = st.file_uploader(
                "JSON 파일을 선택하세요",
                type=['json'],
                help="JSON 형식의 파일을 업로드하세요."
            )
            
            if uploaded_file is not None:
                try:
                    data = json.load(uploaded_file)
                    st.success(f"✅ 파일 로드 성공: {uploaded_file.name}")
                    
                    # 데이터 미리보기
                    with st.expander("📊 데이터 미리보기"):
                        if isinstance(data, dict):
                            st.json(data)
                        elif isinstance(data, list):
                            st.write(f"총 {len(data)}명의 데이터")
                            if len(data) > 0:
                                st.json(data[0])  # 첫 번째 항목만 표시
                except Exception as e:
                    st.error(f"❌ 파일 읽기 오류: {e}")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        else:  # JSON 텍스트 입력
            st.markdown("JSON 데이터를 직접 입력하거나 샘플을 사용하세요:")
            
            # 샘플 버튼들
            col_sample1, col_sample2, col_sample3 = st.columns(3)
            
            with col_sample1:
                if st.button("👤 단일 인물 샘플"):
                    sample = {
                        "이름": "홍길동",
                        "총경력": "5년 3개월",
                        "포지션": "백엔드 개발자",
                        "나이(탄생연도)": "1990년",
                        "성별": "남",
                        "최종학력(학교-전공)": "서울대학교 컴퓨터공학과",
                        "최종직장": "카카오",
                        "직급/주요업무": "시니어 개발자 / API 개발",
                        "전화번호": "010-1234-5678",
                        "이메일": "hong@example.com",
                        "핵심역량": "Python, Django, AWS, Docker"
                    }
                    st.session_state['json_input'] = json.dumps(sample, ensure_ascii=False, indent=2)
            
            with col_sample2:
                if st.button("👥 여러 인물 샘플"):
                    sample = [
                        {
                            "이름": "김철수",
                            "총경력": "3년 6개월",
                            "포지션": "프론트엔드 개발자",
                            "나이(탄생연도)": "1995년",
                            "성별": "남",
                            "전화번호": "010-2345-6789",
                            "이메일": "kim@example.com"
                        },
                        {
                            "이름": "이영희",
                            "총경력": "7년 2개월",
                            "포지션": "데이터 분석가",
                            "나이(탄생연도)": "1988년",
                            "성별": "여",
                            "전화번호": "010-3456-7890",
                            "이메일": "lee@example.com"
                        }
                    ]
                    st.session_state['json_input'] = json.dumps(sample, ensure_ascii=False, indent=2)
            
            with col_sample3:
                if st.button("🗑️ 초기화"):
                    st.session_state['json_input'] = ""
            
            # JSON 텍스트 입력
            json_input = st.text_area(
                "JSON 데이터:",
                height=300,
                value=st.session_state.get('json_input', ''),
                placeholder='{"이름": "홍길동", "총경력": "5년", ...}'
            )
            
            # JSON 검증
            if json_input.strip():
                try:
                    data = json.loads(json_input)
                    st.success("✅ 유효한 JSON 형식입니다!")
                    
                    # 데이터 타입 표시
                    if isinstance(data, dict):
                        st.info(f"📄 단일 인물 데이터 (필드 수: {len(data)})")
                    elif isinstance(data, list):
                        st.info(f"👥 여러 인물 데이터 ({len(data)}명)")
                    
                except json.JSONDecodeError as e:
                    st.error(f"❌ JSON 형식 오류: {e}")
                    data = None
    
    with col2:
        st.header("🚀 업로드 실행")
        
        # 업로드 버튼
        upload_disabled = not (
            st.session_state.get('connection_verified', False) and 
            data is not None
        )
        
        if st.button(
            "📤 Notion에 업로드",
            disabled=upload_disabled,
            help="연결 테스트와 데이터 입력을 완료한 후 업로드하세요."
        ):
            uploader = st.session_state.get('uploader')
            if uploader and data:
                
                # 진행률 표시용 플레이스홀더
                progress_placeholder = st.empty()
                log_placeholder = st.empty()
                
                if isinstance(data, dict):
                    # 단일 인물 처리
                    with st.spinner("업로드 중..."):
                        success, message = uploader.upload_person(data)
                        
                        if success:
                            st.success(message)
                        else:
                            st.error(message)
                
                elif isinstance(data, list):
                    # 여러 인물 처리
                    total = len(data)
                    success_count = 0
                    
                    progress_bar = progress_placeholder.progress(0)
                    log_messages = []
                    
                    for i, person_data in enumerate(data):
                        # 진행률 업데이트
                        progress = (i + 1) / total
                        progress_bar.progress(progress)
                        
                        # 업로드 실행
                        success, message = uploader.upload_person(person_data)
                        
                        if success:
                            success_count += 1
                            log_messages.append(f"✅ {message}")
                        else:
                            log_messages.append(f"❌ {message}")
                        
                        # 로그 업데이트
                        log_placeholder.text_area(
                            "처리 로그:",
                            value="\n".join(log_messages[-5:]),  # 최근 5개만 표시
                            height=150
                        )
                        
                        time.sleep(0.1)  # 시각적 효과
                    
                    # 최종 결과
                    if success_count == total:
                        st.success(f"🎉 모든 데이터 업로드 완료! ({success_count}/{total})")
                    else:
                        st.warning(f"⚠️ 부분 성공: {success_count}/{total} 업로드 완료")
                    
                    # 상세 로그
                    with st.expander("📋 상세 로그 보기"):
                        for msg in log_messages:
                            st.text(msg)
        
        # 도움말
        st.markdown("---")
        st.subheader("💡 사용 가이드")
        
        with st.expander("🔧 설정 방법"):
            st.markdown("""
            1. **Notion Integration 생성**
               - https://www.notion.so/my-integrations 접속
               - "New integration" 클릭
               - 이름 설정 후 생성
               - "Internal Integration Token" 복사
            
            2. **데이터베이스 공유**
               - 대상 데이터베이스 페이지 열기
               - 우상단 "공유" → Integration 추가
               - Database ID 복사 (URL에서 확인 가능)
            """)
        
        with st.expander("📝 JSON 형식 가이드"):
            st.markdown("""
            **지원하는 필드들:**
            - 이름 (필수)
            - 총경력
            - 포지션
            - 나이(탄생연도)
            - 성별
            - 최종학력(학교-전공)
            - 최종직장
            - 직급/주요업무
            - 전화번호
            - 이메일
            - 핵심역량
            
            **단일 인물:** `{"이름": "홍길동", ...}`
            
            **여러 인물:** `[{"이름": "홍길동"}, {"이름": "김철수"}]`
            """)

if __name__ == "__main__":
    main()