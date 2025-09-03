import streamlit as st
import os
from PIL import Image
import io
import json
import tempfile

try:
    import fitz  # PyMuPDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    st.warning("⚠️ PyMuPDF가 설치되지 않았습니다. PDF 파일 지원이 제한됩니다.")

# Google Gemini API
import google.generativeai as genai
from google.generativeai import types

# Notion API
from notion_client import Client

# 페이지 설정
st.set_page_config(
    page_title="이력서 파서 & Notion 업로더",
    page_icon="📄",
    layout="wide"
)

# 제목 및 설명
st.title("📄 이력서 자동 파싱 시스템")
st.markdown("이력서 파일을 업로드하면 Google Gemini AI로 정보를 추출하여 Notion 데이터베이스에 자동 저장합니다.")

# 사이드바에 설정 정보 입력
st.sidebar.header("🔑 API 설정")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")
notion_api_key = st.sidebar.text_input("Notion API Key", type="password")
notion_db_id = st.sidebar.text_input("Notion Database ID")

# API 설정 확인
api_configured = gemini_api_key and notion_api_key and notion_db_id

if not api_configured:
    st.warning("⚠️ 사이드바에서 API 키와 Notion 데이터베이스 ID를 입력해주세요.")

# 이력서 정보 추출을 위한 JSON 스키마 정의
RESUME_SCHEMA = {
    "type": "object",
    "properties": {
        "이름": {"type": "string"},
        "나이/탄생연도": {"type": "string"},
        "성별": {"type": "string"},
        "총경력": {"type": "string"},
        "최종직장": {"type": "string"},
        "최종학력(전공)": {"type": "string"},
        "직급/주요업무": {"type": "string"},
        "전화번호": {"type": "string"},
        "이메일": {"type": "string"},
        "핵심역량": {"type": "string"},
        "포지션": {"type": "string"}
    },
    "required": ["이름"]
}

def parse_file_with_gemini(file_path, gemini_api_key):
    """
    파일에서 이력서 정보를 추출하고 JSON으로 변환합니다.
    """
    # Gemini API 초기화
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    
    # 프롬프트 구성
    prompt = """
    당신은 전문적인 이력서 정보 추출 전문가입니다. 첨부된 이력서 문서에서 다음 정보를 정확하게 추출하여 지정된 JSON 스키마 형식으로 반환하세요.
    
    1. 이름
    2. 나이/탄생연도 (예: "1990년" 또는 "32세")
    3. 성별
    4. 총경력 (예: "5년", "3년 6개월")
    5. 최종직장
    6. 최종학력(전공) (예: "서울대학교 컴퓨터공학과")
    7. 직급/주요업무
    8. 전화번호
    9. 이메일
    10. 핵심역량 (기술스택, 핵심 능력을 쉼표로 구분)
    11. 포지션 (지원 직무나 희망 포지션, 쉼표로 구분 가능)
    
    만약 특정 정보를 찾을 수 없거나 관련이 없으면 해당 필드의 값은 null로 처리하세요.
    정확한 JSON 형식으로만 응답하세요.
    """
    
    contents = [prompt]
    
    # 파일 확장자 확인 및 처리
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == '.pdf':
        if not PDF_SUPPORT:
            raise Exception("PDF 처리를 위해서는 PyMuPDF가 필요합니다. 'pip install PyMuPDF'로 설치해주세요.")
        
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            
            # 이미지 바이트를 Gemini API의 Part로 변환
            img_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
            contents.append(img_part)
        doc.close()
    else:
        # 기타 이미지 파일 처리 (jpeg, png, etc.)
        with open(file_path, 'rb') as f:
            image_bytes = f.read()
            mime_type = f"image/{file_extension.replace('.', '')}"
            if file_extension == '.jpg':
                mime_type = "image/jpeg"
            img_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            contents.append(img_part)

    try:
        response = model.generate_content(
            contents=contents,
            generation_config=types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=RESUME_SCHEMA
            )
        )
        # JSON 응답을 파이썬 딕셔너리로 파싱
        extracted_data = json.loads(response.text)
        return extracted_data
        
    except Exception as e:
        st.error(f"Gemini API 호출 중 오류 발생: {e}")
        return None

def upload_to_notion(data, notion_api_key, notion_db_id):
    """
    추출된 JSON 데이터를 Notion 데이터베이스에 새 페이지로 업로드합니다.
    """
    if not data:
        st.error("업로드할 데이터가 없습니다.")
        return False
        
    try:
        # Notion API 초기화
        notion_client = Client(auth=notion_api_key)
        
        # 데이터베이스 정보 조회 (속성 타입 확인용)
        try:
            db_info = notion_client.databases.retrieve(database_id=notion_db_id)
        except Exception as e:
            st.error(f"데이터베이스 정보 조회 실패: {e}")
            return None
        
        # Notion 데이터베이스 속성(properties) 객체 구성
        properties = _build_properties(data, db_info)
        
        # Notion 데이터베이스에 새 페이지 생성
        response = notion_client.pages.create(
            parent={"database_id": notion_db_id},
            properties=properties
        )
        
        return response
        
    except Exception as e:
        st.error(f"Notion API 호출 중 오류 발생: {e}")
        return None

def _build_properties(person_data, db_info):
    """Notion 속성 구성"""
    properties = {}
    
    # 이름 (Title) - 필수 필드
    if person_data.get("이름"):
        properties["이름"] = {
            "title": [{"text": {"content": str(person_data["이름"])}}]
        }
    
    # 이메일
    if person_data.get("이메일"):
        properties["이메일"] = {"email": person_data["이메일"]}
    
    # 전화번호
    if person_data.get("전화번호"):
        phone = _format_phone(person_data["전화번호"])
        try:
            properties["전화번호"] = {"phone_number": phone}
        except:
            properties["전화번호"] = {"rich_text": [{"text": {"content": phone}}]}
    
    # Select 필드들
    select_fields = {
        "나이/탄생연도": person_data.get("나이/탄생연도"),
        "성별": person_data.get("성별"),
    }
    
    for field, value in select_fields.items():
        if value and field in db_info['properties']:
            if db_info['properties'][field]['type'] == 'select':
                properties[field] = {"select": {"name": str(value)}}
    
    # Rich Text 필드들
    rich_text_fields = {
        "총경력": person_data.get("총경력"),
        "최종학력(전공)": person_data.get("최종학력(전공)"),
        "최종직장": person_data.get("최종직장"),
        "직급/주요업무": person_data.get("직급/주요업무"),
        "핵심역량": person_data.get("핵심역량"),
        "포지션": person_data.get("포지션"),
    }
    
    for field, value in rich_text_fields.items():
        if value and field in db_info['properties']:
            prop_type = db_info['properties'][field]['type']
            if prop_type == 'rich_text':
                properties[field] = {"rich_text": [{"text": {"content": str(value)}}]}
            elif prop_type == 'multi_select' and field == "포지션":
                values = [v.strip() for v in str(value).split(',')]
                properties[field] = {"multi_select": [{"name": val} for val in values if val]}
    
    return properties

def _format_phone(phone):
    """전화번호 형식 정리"""
    phone_cleaned = ''.join(filter(str.isdigit, str(phone)))
    
    if len(phone_cleaned) == 11 and phone_cleaned.startswith('010'):
        return f"{phone_cleaned[:3]}-{phone_cleaned[3:7]}-{phone_cleaned[7:]}"
    
    return str(phone)

# 메인 애플리케이션
def main():
    # 파일 업로드
    supported_types = ['png', 'jpg', 'jpeg']
    if PDF_SUPPORT:
        supported_types.append('pdf')
    
    uploaded_file = st.file_uploader(
        "이력서 파일을 업로드하세요",
        type=supported_types,
        help="PNG, JPG, JPEG" + (" 및 PDF" if PDF_SUPPORT else "") + " 형식을 지원합니다"
    )
    
    if uploaded_file is not None:
        # 파일 정보 표시
        st.success(f"✅ 파일 업로드 완료: {uploaded_file.name}")
        
        # 파일 미리보기 (이미지인 경우)
        if uploaded_file.type.startswith('image'):
            st.image(uploaded_file, caption="업로드된 이력서", use_column_width=True)
        
        # 처리 버튼
        if st.button("🚀 이력서 파싱 시작", disabled=not api_configured):
            if not api_configured:
                st.error("API 설정을 완료해주세요.")
                return
            
            # 진행 상황 표시
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # 임시 파일로 저장
                status_text.text("파일 처리 중...")
                progress_bar.progress(20)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name
                
                # Gemini API로 정보 추출
                status_text.text("Gemini AI로 정보 추출 중...")
                progress_bar.progress(60)
                
                extracted_data = parse_file_with_gemini(tmp_file_path, gemini_api_key)
                
                if extracted_data:
                    # 추출된 데이터 표시
                    st.subheader("📊 추출된 정보")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.json(extracted_data)
                    
                    with col2:
                        st.write("**추출된 정보 요약:**")
                        for key, value in extracted_data.items():
                            if value is not None:
                                if key == "핵심역량" and "," in str(value):
                                    skills = [skill.strip() for skill in str(value).split(",")]
                                    st.write(f"• **{key}**: {', '.join(skills)}")
                                elif key == "포지션" and "," in str(value):
                                    positions = [pos.strip() for pos in str(value).split(",")]
                                    st.write(f"• **{key}**: {', '.join(positions)}")
                                else:
                                    st.write(f"• **{key}**: {value}")
                    
                    # Notion 업로드
                    status_text.text("Notion 데이터베이스에 업로드 중...")
                    progress_bar.progress(80)
                    
                    notion_response = upload_to_notion(extracted_data, notion_api_key, notion_db_id)
                    
                    if notion_response:
                        progress_bar.progress(100)
                        status_text.text("완료!")
                        st.success("🎉 이력서 정보가 Notion 데이터베이스에 성공적으로 저장되었습니다!")
                        
                        # Notion 페이지 링크 제공
                        if 'url' in notion_response:
                            st.markdown(f"[📋 Notion에서 확인하기]({notion_response['url']})")
                    else:
                        st.error("Notion 업로드에 실패했습니다.")
                
                else:
                    st.error("정보 추출에 실패했습니다.")
                
                # 임시 파일 삭제
                os.unlink(tmp_file_path)
                
            except Exception as e:
                st.error(f"처리 중 오류가 발생했습니다: {e}")
                progress_bar.progress(0)
                status_text.text("")

# 사이드바에 추가 정보
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Notion 데이터베이스 설정")
st.sidebar.markdown("""
Notion 데이터베이스에 다음 속성들이 있어야 합니다:
- **이름** (Title)
- **나이/탄생연도** (Select 또는 Rich Text)  
- **성별** (Select)
- **총경력** (Rich Text)
- **최종직장** (Rich Text)
- **최종학력(전공)** (Rich Text)
- **직급/주요업무** (Rich Text)
- **전화번호** (Phone Number)
- **이메일** (Email)
- **핵심역량** (Rich Text)
- **포지션** (Multi-select)
""")

st.sidebar.markdown("### 🔧 설정 방법")
st.sidebar.markdown("""
1. **Gemini API Key**: Google AI Studio에서 발급
2. **Notion API Key**: Notion Integration에서 생성
3. **Database ID**: Notion 데이터베이스 URL에서 추출
""")

# 메인 함수 실행
if __name__ == "__main__":
    main()