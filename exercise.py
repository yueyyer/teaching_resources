import streamlit as st
import openai
from dotenv import load_dotenv
import os
import json
import unicodedata
from fpdf import FPDF, HTMLMixin
import markdown
from word2picture import generate_picture_by_text
from ocr_scenes_demo import ocr_image_url
from sidebar_css import load_sidebar_css
import requests
import wikipedia

# 定义MyFPDF用于支持write_html
class MyFPDF(FPDF, HTMLMixin):
    pass
import base64
import time
import sqlite3
import datetime
from pathlib import Path
import requests
from PIL import Image
import io
import speech_recognition as sr
from gtts import gTTS
import tempfile
import pandas as pd

# 页面配置
st.set_page_config(
    page_title="乡村教育AI智能系统",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Prompts (建议放在单独的prompts.py文件中) ---
# 为了方便你直接运行，我暂时把它们放在这里

PROMPT_TEMPLATES = {
    "课程大纲": """
    你是一位经验丰富的课程设计师。请根据以下要求，为一门课程设计一个详细、结构化的大纲。
    - 课程主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 大纲需要包含合理的模块划分，每个模块下有具体的章节或知识点。逻辑清晰，层层递进。只输出标准 Markdown，不要输出 HTML 标签，不要用代码块包裹内容。
    """,
    "教学PPT": """
    你是一位PPT制作专家。请根据以下主题，生成一份教学PPT的核心内容大纲。
    - 主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 为每一页PPT提供标题和核心要点（3-5点）。内容应简洁、易于理解，并建议在何处使用图表或图像。总页数在10-15页之间。只输出标准 Markdown，不要输出 HTML 标签，不要用代码块包裹内容。
    """,
    "练习题目": """
    你是一位资深的命题专家。请根据以下要求，设计一套练习题。
    - 知识点: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 生成5-10道题目，包含至少2种题型（如选择题、填空题、简答题）。题目需覆盖核心知识点，并附上标准答案和解析。只输出标准 Markdown，不要输出 HTML 标签，不要用代码块包裹内容。
    """,
    "案例分析": """
    你是一位行业分析师和教育家。请根据以下场景，撰写一份教学案例分析。
    - 案例主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 案例需包含背景介绍、核心问题、分析过程和结论/启示。内容要具有深度和启发性。只输出标准 Markdown，不要输出 HTML 标签，不要用代码块包裹内容。
    """,
    "实验指导": """
    你是一位实验室指导教师。请根据以下内容，编写一份清晰的实验指导手册。
    - 实验名称: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 指导需包含实验目的、实验原理、所需器材、详细操作步骤、注意事项和数据记录表格。只输出标准 Markdown，不要输出 HTML 标签，不要用代码块包裹内容。
    """
}

# --- 数据库初始化与操作 ---
# 使用绝对路径，确保数据库文件位置固定
DB_FILE = os.path.abspath("teaching_resources.db")
RESOURCE_DIR = Path("resource_files")
RESOURCE_DIR.mkdir(exist_ok=True)

def init_database():
    """初始化SQLite数据库"""
    try:
        # 确保数据库文件所在目录存在
        db_dir = os.path.dirname(DB_FILE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT,
                    file_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT,
                    description TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    resource_id INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS resource_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute("PRAGMA table_info(resource_links)")
            columns = [row[1] for row in cursor.fetchall()]
            if "image_path" not in columns:
                cursor.execute("ALTER TABLE resource_links ADD COLUMN image_path TEXT")
            conn.commit()
            print(f"数据库初始化成功: {DB_FILE}")
            return True
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        st.error(f"数据库初始化失败: {e}")
        return False

def log_action(action, resource_id=None, details=""):
    """记录用户操作日志"""
    try:
        # 确保数据库存在
        if not init_database():
            return False

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_logs (action, resource_id, details) VALUES (?, ?, ?)",
                (action, resource_id, details)
            )
            # 立即提交事务
            conn.commit()
            print(f"日志已记录: {action} - {details}")
            return True

    except Exception as e:
        print(f"记录日志失败: {e}")
        st.error(f"记录日志失败: {e}")
        return False

def save_resource_to_db(title, resource_type, category, content=None, file_path=None, tags="", description=""):
    """保存资源到数据库"""
    try:
        # 输入验证
        if not title or not title.strip():
            raise ValueError("标题不能为空")
        if not resource_type or not resource_type.strip():
            raise ValueError("资源类型不能为空")
        if not category or not category.strip():
            raise ValueError("分类不能为空")

        # 确保数据库存在
        if not init_database():
            return None

        print(f"开始保存资源: {title}, 类型: {resource_type}, 分类: {category}")

        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # 插入资源数据
            cursor.execute(
                "INSERT INTO resources (title, type, category, content, file_path, tags, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title.strip(), resource_type.strip(), category.strip(), content, str(file_path) if file_path else None,
                 tags, description)
            )
            resource_id = cursor.lastrowid

            # 立即提交事务
            conn.commit()

            # 验证插入是否成功
            cursor.execute("SELECT COUNT(*) FROM resources WHERE id = ?", (resource_id,))
            count = cursor.fetchone()[0]

            if count == 1:
                # 记录日志
                log_success = log_action("CREATE", resource_id, f"Created {resource_type}: {title}")
                print(f"资源已成功保存到数据库，ID: {resource_id}, 日志记录: {log_success}")
                return resource_id
            else:
                print("资源保存验证失败")
                return None

    except Exception as e:
        error_msg = f"保存资源时发生错误: {str(e)}"
        print(error_msg)
        st.error(error_msg)
        return None

def get_resources_from_db(search_term="", category=None, resource_type=None):
    """从数据库获取资源，支持搜索和筛选"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            query = "SELECT id, title, type, category, created_at, description, file_path, content FROM resources WHERE 1=1"
            params = []
            if search_term:
                query += " AND (title LIKE ? OR description LIKE ? OR tags LIKE ?)"
                params.extend([f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"])
            if category and category != "所有":
                query += " AND category = ?"
                params.append(category)
            if resource_type and resource_type != "所有":
                query += " AND type = ?"
                params.append(resource_type)
            query += " ORDER BY created_at DESC"

            results = cursor.execute(query, params).fetchall()
            print(f"从数据库获取到 {len(results)} 个资源")
            return results
    except Exception as e:
        error_msg = f"获取资源失败: {e}"
        print(error_msg)
        st.error(error_msg)
        return []

def delete_resource_from_db(resource_id):
    """从数据库删除资源并删除关联文件"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # 先获取文件路径
            cursor.execute("SELECT file_path, title, type FROM resources WHERE id = ?", (resource_id,))
            result = cursor.fetchone()
            if result and result[0]:
                file_to_delete = Path(result[0])
                if file_to_delete.exists():
                    file_to_delete.unlink()  # 删除文件

            # 删除数据库记录
            cursor.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
            conn.commit()
            log_action("DELETE", resource_id, f"Deleted resource ID {resource_id} ({result[2]}: {result[1]})")
            return True
    except Exception as e:
        st.error(f"删除资源失败: {e}")
        return False


def check_database_status():
    """检查数据库状态"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            # 检查资源数量
            cursor.execute("SELECT COUNT(*) FROM resources")
            resource_count = cursor.fetchone()[0]

            # 检查日志数量
            cursor.execute("SELECT COUNT(*) FROM user_logs")
            log_count = cursor.fetchone()[0]

            return True, f"数据库正常 - 表: {len(tables)}, 资源: {resource_count}, 日志: {log_count}"
    except Exception as e:
        return False, f"数据库错误: {e}"

def get_db_stats():
    """获取数据库统计信息"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            total_resources = cursor.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            resources_by_type = cursor.execute("SELECT type, COUNT(*) FROM resources GROUP BY type").fetchall()
            resources_by_category = cursor.execute(
                "SELECT category, COUNT(*) FROM resources GROUP BY category").fetchall()
            logs = cursor.execute(
                "SELECT action, details, timestamp FROM user_logs ORDER BY timestamp DESC LIMIT 10").fetchall()
            return total_resources, dict(resources_by_type), dict(resources_by_category), logs
    except Exception as e:
        st.error(f"获取统计信息失败: {e}")
        return 0, {}, {}, []

# 新增：资源链接管理功能
def save_resource_link(title, link_type, url, description="", image_path=None):
    """保存资源链接到数据库"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO resource_links (title, link_type, url, description, image_path) VALUES (?, ?, ?, ?, ?)",
                (title, link_type, url, description, image_path)
            )
            link_id = cursor.lastrowid
            conn.commit()
            log_action("CREATE_LINK", link_id, f"Created {link_type} link: {title}")
            return link_id
    except Exception as e:
        st.error(f"保存链接失败: {e}")
        return None

def get_resource_links(link_type=None):
    """获取资源链接"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            if link_type and link_type != "所有":
                query = "SELECT id, title, link_type, url, description, image_path, created_at FROM resource_links WHERE link_type = ? ORDER BY created_at DESC"
                return cursor.execute(query, (link_type,)).fetchall()
            else:
                query = "SELECT id, title, link_type, url, description, image_path, created_at FROM resource_links ORDER BY created_at DESC"
                return cursor.execute(query).fetchall()
    except Exception as e:
        st.error(f"获取链接失败: {e}")
        return []

def delete_resource_link(link_id):
    """删除资源链接"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, link_type FROM resource_links WHERE id = ?", (link_id,))
            result = cursor.fetchone()
            cursor.execute("DELETE FROM resource_links WHERE id = ?", (link_id,))
            conn.commit()
            log_action("DELETE_LINK", link_id, f"Deleted link: {result[0]} ({result[1]})")
    except Exception as e:
        st.error(f"删除链接失败: {e}")


# --- 多模态与文件处理函数 ---

def generate_pdf(content, filename):
    """将Markdown内容渲染为PDF，保留样式"""
    pdf = MyFPDF()
    pdf.add_page()

    font_path = os.path.join(os.path.dirname(__file__), "simsun.ttf")
    try:
        # 注册所有样式
        pdf.add_font('simsun', '', font_path, uni=True)
        pdf.add_font('simsun', 'B', font_path, uni=True)
        pdf.add_font('simsun', 'I', font_path, uni=True)
        pdf.add_font('simsun', 'BI', font_path, uni=True)
        pdf.set_font('simsun', '', 12)
    except RuntimeError:
        st.warning("未找到中文字体 'simsun.ttf'，PDF中的中文可能无法正确显示。请下载并放置该字体文件到项目目录。")
        pdf.set_font('Arial', '', 12)

    html = markdown.markdown(content)
    pdf.write_html(html)
    pdf_bytes = pdf.output(dest="S")
    # 关键：如果是bytearray，转成bytes
    if isinstance(pdf_bytes, bytearray):
        pdf_bytes = bytes(pdf_bytes)

    # 保存PDF文件到本地
    pdf_path = RESOURCE_DIR / filename
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)

    return pdf_bytes, pdf_path

def text_to_speech(text, language='zh'):
    """文本转语音"""
    try:
        tts = gTTS(text=text, lang=language, slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir=str(RESOURCE_DIR)) as tmp_file:
            tts.save(tmp_file.name)
            return tmp_file.name
    except Exception as e:
        st.error(f"语音合成失败: {e}")
        return None

def speech_to_text(audio_file):
    """语音转文本"""
    r = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file) as source:
            audio = r.record(source)
        # 优先使用Google API，如果不行可以换成其他
        text = r.recognize_google(audio, language='zh-CN')
        return text
    except sr.UnknownValueError:
        st.error("语音识别无法理解音频内容")
        return None
    except sr.RequestError as e:
        st.error(f"无法从Google语音识别服务请求结果; {e}")
        return None
    except Exception as e:
        st.error(f"语音识别失败: {e}")
        return None

def upload_image_to_smms(img_bytes):
    url = "https://sm.ms/api/v2/upload"
    files = {'smfile': ('image.png', img_bytes)}
    resp = requests.post(url, files=files)
    data = resp.json()
    print("sm.ms返回：", data)  # 添加这一行
    if data['success']:
        return data['data']['url']
    else:
        st.error(f"图片上传失败: {data.get('message', '未知错误')}")
        return None


DASHSCOPE_API_KEY = "sk-060679f32afd48798bd98af3118dfc5b"  # 🔐 请替换成你自己的 DashScope Key

import base64
import json

def recognize_image_with_dashscope(img_bytes):
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 将图片编码为 base64，并转成 data:image/png;base64,... 形式
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    image_data_url = f"data:image/png;base64,{img_base64}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    }

    body = {
        "model": "qwen-vl-max",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": "请描述这张图片的内容"
                    }
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, data=json.dumps(body))

    if response.status_code != 200:
        print(f"❌ 请求失败: {response.status_code}")
        print(response.text)
        return None

    try:
        data = response.json()
        print("✅ DashScope返回：", data)
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print("⚠️ JSON解析失败：", e)
        print(response.text)
        return None

# --- UI & 页面渲染 ---

def load_custom_css():
    st.markdown("""
    <style>
    /* 全局样式 */  
    .main { padding-top: 0.5rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 10vh; }
    #MainMenu, footer, header {visibility: hidden;}
    /* 主标题样式 */
    .main-title { text-align: center; color: white; font-size: 2.5rem; font-weight: 800; margin-bottom: 1.5rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); background: linear-gradient(45deg, #FFD700, #FFA500); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    /* 卡片容器样式 */
    .card-container { background: rgba(255, 255, 255, 0.95); border-radius: 15px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 15px 35px rgba(0,0,0,0.1); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.3s ease; }
    .card-container:hover { transform: translateY(-3px); box-shadow: 0 20px 40px rgba(0,0,0,0.15); }
    /* 按钮增强样式 */
    .stButton > button { background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; border-radius: 12px; padding: 0.75rem 2rem; font-size: 1rem; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3); cursor: pointer; }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4); }
    /* 成功消息样式 */
    .success-message { background: linear-gradient(45deg, #28a745, #20c997); color: white; padding: 0.5rem; border-radius: 10px; margin: 0.5rem 0; text-align: center; animation: slideIn 0.5s ease-out; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
    /* 资源预览样式 */
    .resource-preview { border: 1px solid #e9ecef; border-radius: 10px; padding: 1rem; margin: 0.5rem 0; background: #f8f9fa; transition: all 0.3s ease; }
    .resource-preview:hover { border-color: #667eea; background: #ffffff; }
    /* 多模态输入区域 */
    .multimodal-input { background: linear-gradient(135deg, #f1f3f4, #e8eaf6); border-radius: 15px; padding: 1.5rem; margin-top: 1rem; border: 2px dashed #667eea; }
    /* 自定义信息块样式 */
    .custom-info-block {
        background: linear-gradient(90deg, #e3f0ff 0%, #b3d8fd 100%);
        border-left: 6px solid #3399ff;
        border-radius: 12px;
        padding: 2rem 1rem;
        margin: 1.5rem 0;
        color: #225588;
        font-size: 1.4rem;
        font-weight: 600;
        text-align: center;
        box-shadow: 0 4px 18px rgba(51,153,255,0.08);
        letter-spacing: 1px;
    }

    /* 仅缩小生成教学内容按钮 */
    div[data-testid="stButton"][id^="gen_content_btn"] button {
        min-width: 120px !important;
        max-width: 180px !important;
        width: 160px !important;
        height: 2.2rem !important;
        font-size: 1.05rem !important;
        padding: 0.3rem 1.2rem !important;
        border-radius: 8px !important;
    }
    /* 链接管理样式 */
    .link-item {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        transition: all 0.3s ease;
    }
    .link-item:hover {
        background: #e9ecef;
        border-color: #6c757d;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("""
    <style>
    /* 学习路径容器 */
    .learning-prompt {
        background: #E8F5E9;
        border-radius: 12px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #4CAF50;
    }
    .learning-prompt h3 {
        color: #2E7D32;
        margin-top: 0;
    }
    .learning-prompt p {
        margin: 0.8rem 0;
        color: #388E3C;
    }
    /* 阶段容器 */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"] {
        background: rgba(76, 175, 80, 0.05);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 3px solid #4CAF50;
        transition: all 0.3s ease;
    }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"]:hover {
        background: rgba(76, 175, 80, 0.1);
        transform: translateX(5px);
    }
    </style>
    """, unsafe_allow_html=True)

def page_content_generation():
    """内容生成页面"""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        with st.container():
            st.markdown("---")
            st.markdown("### 🎯 内容配置")
            
            content_type = st.selectbox("选择内容类型", list(PROMPT_TEMPLATES.keys()), help="选择要生成的教学资源类型")
            subject = st.selectbox("学科领域", ["语文", "数学", "英语", "物理", "化学", "生物",  "自然科学"], help="选择相关学科领域")
            edu_level = st.selectbox("教育水平", ["小学", "初中", "高中"], help="选择目标教育水平")
            
            st.markdown("---")
            st.markdown("### 🎤 多模态输入")
            input_method = st.radio("选择输入方式", ["文本输入", "语音输入", "图像输入"], horizontal=True, label_visibility="collapsed")
            
            user_input_text = ""
            user_input_image = None
            
            if input_method == "文本输入":
                user_input_text = st.text_area("请描述您的需求", placeholder=f"例如：为{subject}学科生成一个{edu_level}教育水平的关于...的{content_type}", height=150)
            
            elif input_method == "语音输入":
                uploaded_audio = st.file_uploader("上传音频文件", type=['wav', 'mp3', 'flac'])
                if uploaded_audio:
                    with st.spinner("正在识别语音..."):
                        # 将上传的文件写入临时文件以供识别库使用
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                            tmp_file.write(uploaded_audio.getvalue())
                            recognized_text = speech_to_text(tmp_file.name)
                        os.unlink(tmp_file.name) # 删除临时文件
                        if recognized_text:
                            user_input_text = st.text_area("识别结果（可编辑）", value=recognized_text, height=150)

            elif input_method == "图像输入":
                user_input_image = st.file_uploader("上传图像文件", type=['jpg', 'jpeg', 'png'])
                ocr_result = ""
                if user_input_image:
                    st.image(user_input_image, caption="上传的图像", use_column_width=True)
                    img_bytes = user_input_image.read()
                    if st.button("🔍 自动识别图片内容"):
                        with st.spinner("正在上传图片并识别..."):
                            img_url = recognize_image_with_dashscope(img_bytes)
                            result_text = recognize_image_with_dashscope(img_bytes)
                            if result_text:
                                ocr_result = result_text
                                st.success("图片识别成功！")
                                st.code(ocr_result)
                            else:
                                st.error("识别失败，请检查API Key或图片格式。")
                            # if img_url:
                            #     ocr_bytes = ocr_image_url("uploaded.jpg", img_url)
                            #     try:
                            #         ocr_json = json.loads(ocr_bytes.decode("utf-8"))
                            #         ocr_result = ocr_json.get("data", {}).get("content", "")
                            #         st.success("图片识别成功！")
                            #         st.code(ocr_result)
                            #     except Exception as e:
                            #         st.error(f"OCR解析失败: {e}")
                            # else:
                            #     st.error("图片上传失败，请重试。")
                user_input_text = st.text_area(
                    "请结合图像描述您的需求",
                    value=ocr_result,  # 识别结果自动填入，可编辑
                    placeholder=f"例如：基于上图，生成一个相关的{content_type}...",
                    height=100
                )
        # 把按钮放在最后
        generate_content = st.button("🚀 生成教学内容", use_container_width=True)

        if generate_content and user_input_text.strip():
            with st.spinner("🤖 AI大脑正在思考并生成内容..."):
                try:
                    # 构建提示
                    prompt_template = PROMPT_TEMPLATES.get(content_type, "请根据以下信息生成内容：{user_input}")
                    final_prompt = prompt_template.format(user_input=user_input_text, subject=subject,
                                                          edu_level=edu_level)

                    messages = [
                        {"role": "system", "content": "你是一位专业的教育内容生成专家，擅长创建各种类型的教学资源。"}]

                    # (这是一个简化的RAG/Agent思想) 如果有图片，加入图片信息
                    if user_input_image:
                        # 假设 ocr_result 已获取
                        ocr_text = ""  # 你可以从 st.session_state 或上面识别结果获取
                        if ocr_result:
                            messages.append({"role": "user", "content": f"[图像信息：{ocr_result}] {final_prompt}"})
                        else:
                            messages.append({"role": "user",
                                             "content": f"[图像信息：用户上传了一张图片，并希望基于此进行创作] {final_prompt}"})
                    else:
                        messages.append({"role": "user", "content": final_prompt})

                    response = client.chat.completions.create(
                        model=st.session_state.openai_model,
                        messages=messages
                    )
                    st.session_state.generated_content = response.choices[0].message.content
                except Exception as e:
                    st.error(f"内容生成失败: {e}")
                    st.session_state.generated_content = ""

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown("---")
        st.markdown("### 📝 内容生成区")
        
        if "generated_content" not in st.session_state:
            st.session_state.generated_content = ""

        # 先显示生成结果
        if st.session_state.generated_content:
            st.markdown("#### ✨ 生成结果")
            content = st.session_state.generated_content
# 自动去除开头和结尾的代码块符号
            if content.strip().startswith("```") and content.strip().endswith("```"):
                content = content.strip().strip("`").strip()
            st.markdown(content, unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("#### 🛠️ 后续操作")
            
            save_title = st.text_input("为该资源命名", value=f"{subject}_{content_type}_{datetime.datetime.now().strftime('%H%M')}")
            
            col_save1, col_save2 = st.columns(2)
            with col_save1:
                if st.button("💾 保存到资源库", use_container_width=True):
                    if save_title:
                        res_id = save_resource_to_db(
                            title=save_title,
                            resource_type=content_type,
                            category=subject,
                            content=st.session_state.generated_content,
                            description=user_input_text[:100]
                        )
                        st.success(f"✅ 已保存到资源库 (ID: {res_id})")
                        log_action("SAVE_CONTENT", res_id, save_title)
                    else:
                        st.warning("请输入资源名称后再保存")
            with col_save2:
                pdf_bytes = None
                if st.button("📄 生成并下载PDF（默认命名与路径）", use_container_width=True):
                    pdf_bytes = generate_pdf(st.session_state.generated_content, f"{save_title}.pdf")
                if pdf_bytes:
                    st.download_button(
                        label="点击重命名和自定义路径",
                        data=pdf_bytes[0],  # 只传递pdf_bytes，不要传元组
                        file_name=f"{save_title}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        else:
            st.markdown("""
            <div class="custom-info-block">
                请在左侧配置您的内容需求，然后点击生成按钮。
            </div>
            """, unsafe_allow_html=True)

def page_multimedia_production():
    """多媒体制作页面"""
    st.markdown("---")
    st.markdown("### 🎨 多媒体资源制作中心")
    media_tabs = st.tabs(["🖼️ AI图像生成", "🎵 AI音频合成", "🎬 视频工具 (概念)", "� 图表制作 (概念)", "讯飞OCR识图"])

    with media_tabs[0]: # AI图像生成
        # ...existing code...
        with st.container():
            st.markdown("#### 生成教学图像")
            xfyun_prompt = st.text_area("生图描述", placeholder="例如：物理实验图，一个在倾斜木板上运动的小球", height=120)
            if st.button("✨ 生成图像", use_container_width=True):
                if xfyun_prompt.strip():
                    with st.spinner("正在生成图片..."):
                        APPID = 'b18dc113'
                        APIKEY = '20082c2448c81bcb4fa76a12c6be12fe'
                        APISECRET = 'NjRkNDk5MWUwNmU1MDg5Y2RjZjczOWM2'
                        try:
                            img_path = generate_picture_by_text(
                                xfyun_prompt, APPID, APIKEY, APISECRET, save_dir=str(RESOURCE_DIR)
                            )
                            if img_path:
                                st.image(img_path, caption="您的图像已就绪")
                                with open(img_path, "rb") as f:
                                    st.download_button("📥 下载图片", f, file_name=Path(img_path).name)
                            else:
                                st.error("图片生成失败")
                        except Exception as e:
                            st.error(f"图片生成异常: {e}")
                else:
                    st.warning("请输入描述内容")
        # ...existing code...

    with media_tabs[1]: # AI音频合成
        st.markdown("#### 通过文本生成教学语音")
        tts_text = st.text_area("输入要转换为语音的文本", height=150)
        if st.button("🔊 生成语音", use_container_width=True):
            if tts_text.strip():
                with st.spinner("正在合成语音..."):
                    audio_path = text_to_speech(tts_text)
                    if audio_path:
                        with open(audio_path, "rb") as f:
                            audio_bytes = f.read()
                        st.audio(audio_bytes, format="audio/mp3")
                        st.download_button("📥 下载音频", audio_bytes, file_name="generated_audio.mp3")
                        if st.button("💾 保存至资源库"):
                             res_id = save_resource_to_db(
                                title=f"AI音频: {tts_text[:30]}...",
                                resource_type="音频",
                                category="AI生成",
                                file_path=audio_path,
                                description=tts_text
                            )
                             st.success(f"音频已保存到资源库 (ID: {res_id})")
            else:
                st.warning("请输入文本内容")
    
    with media_tabs[2]:
        st.info("🎬 **视频制作工具** - 这是一个概念演示，展示了未来可能的功能。")
        st.markdown("""
        本模块旨在集成AI视频能力，实现自动化教学视频创作：
        - **PPT转视频**: 上传PPT文件，AI自动为其生成配音和动画，转换成视频。
        - **文本生成视频**: 输入文字脚本，AI匹配素材或生成虚拟场景，制作讲解视频。
        - **智能剪辑**: 上传长视频，AI自动识别关键帧、去除无声片段、添加字幕。
        """)

    with media_tabs[3]:
        st.info("📊 **图表制作工具** - 这是一个概念演示，展示了未来可能的功能。")
        st.markdown("""
        本模块旨在通过自然语言理解，简化数据可视化的过程：
        - **自然语言生成图表**: 输入如“展示A产品过去一年的销售额月度变化折线图”，并上传数据，系统即可自动生成相应图表。
        - **数据分析与洞察**: AI不仅能生成图表，还能对图表数据进行初步分析，指出趋势、异常点等。
        - **多种图表类型**: 支持折线图、柱状图、饼图、散点图等多种常用图表。
        """)
        
    with media_tabs[4]:  # 新增一个Tab
        st.markdown("#### 讯飞OCR识图")
        ocr_mode = st.radio("选择识图方式", ["图片URL", "本地上传"], horizontal=True)
        if ocr_mode == "图片URL":
            img_url = st.text_input("请输入图片URL")
            if st.button("🔍 识别图片URL", use_container_width=True):
                if img_url.strip():
                    with st.spinner("正在识别..."):
                        result = ocr_image_url("img.jpg", img_url)
                        st.write("接口原始返回：")
                        st.code(result)
                else:
                    st.warning("请输入图片URL")
        else:
            uploaded_img = st.file_uploader("上传图片", type=['jpg', 'jpeg', 'png'])
            if st.button("🔍 识别本地图片", use_container_width=True):
                if uploaded_img:
                    # 这里建议你先将图片上传到图床，获得url后再用ocr_image_url
                    st.info("本地图片识别暂未实现直传，请先上传到图床获得url")
                else:
                    st.warning("请上传图片文件")
        
    st.markdown('</div>', unsafe_allow_html=True)

def page_resource_management():
    """资源管理页面"""
    st.markdown("---")
    st.markdown("### 📚 教学资源管理中心")

    # 主要资源管理
    resource_tabs = st.tabs(["📁 资源库管理", "🔗 资源链接共享"])

    with resource_tabs[0]:
        # 筛选和搜索栏
        st.markdown("#### 筛选与搜索")
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_term = st.text_input("搜索资源（按标题、描述、标签）", label_visibility="collapsed",
                                        placeholder="输入关键词搜索...")
        with col2:
            # 从数据库动态获取分类和类型
            all_res = get_resources_from_db()
            categories = ["所有"] + sorted(list(set([r[3] for r in all_res])))
            types = ["所有"] + sorted(list(set([r[2] for r in all_res])))

            filter_category = st.selectbox("按学科筛选", options=categories, label_visibility="collapsed")
        with col3:
            filter_type = st.selectbox("按类型筛选", options=types, label_visibility="collapsed")

        # 刷新按钮
        if st.button("🔄 刷新资源列表", use_container_width=True):
            st.rerun()

        # 获取并显示资源
        resources = get_resources_from_db(search_term, filter_category, filter_type)
        st.markdown(f"--- \n#### 找到 {len(resources)} 个资源")

        if not resources:
            st.info("未找到匹配的资源。尝试调整筛选条件或创建新资源。")

            # 显示数据库状态
            with st.expander("🔧 数据库状态检查"):
                db_ok, db_msg = check_database_status()
                if db_ok:
                    st.success(db_msg)
                else:
                    st.error(db_msg)
        else:
            for res in resources:
                res_id, title, res_type, category, created_at, description, file_path, content = res
                with st.container():
                    st.markdown('<div class="resource-preview">', unsafe_allow_html=True)
                    col_title, col_button = st.columns([4, 1])
                    with col_title:
                        st.subheader(f"{title}")
                        st.caption(
                            f"ID: {res_id} | 类型: {res_type} | 学科: {category} | 创建于: {created_at.split('.')[0]}")

                    with col_button:
                        # 使用唯一key来避免Streamlit的按钮冲突
                        if st.button("🗑️ 删除", key=f"del_{res_id}", use_container_width=True):
                            try:
                                if delete_resource_from_db(res_id):
                                    st.success(f"资源 ID:{res_id} 已删除。")
                                    time.sleep(1)  # 给用户时间看到成功消息
                                    st.rerun()  # 刷新页面
                                else:
                                    st.error("删除失败")
                            except Exception as e:
                                st.error(f"删除失败: {e}")

                    with st.expander("查看详情/预览"):
                        if description:
                            st.markdown(f"**需求描述:** {description}")
                        if res_type in ["图像", "音频"] and file_path:
                            if Path(file_path).exists():
                                if res_type == "图像":
                                    st.image(str(file_path))
                                else:
                                    with open(file_path, "rb") as f:
                                        st.audio(f.read(), format="audio/mp3")
                            else:
                                st.warning("文件丢失或已被删除。")
                        elif content:
                            st.markdown(content)
                        else:
                            st.write("此资源无内容预览。")

                    st.markdown('</div>', unsafe_allow_html=True)

    with resource_tabs[1]:
        # 新增的资源链接管理功能
        st.markdown("#### 🔗 教学资源链接共享")
        st.markdown("管理教科书、教学课程、教学直播等外部资源链接")

        # 添加新链接
        with st.expander("➕ 添加新的资源链接", expanded=False):
            col_add1, col_add2 = st.columns(2)
            with col_add1:
                link_title = st.text_input("链接标题")
                link_type = st.selectbox("链接类型", ["教科书", "教学课程", "教学直播", "其他"])
            with col_add2:
                link_url = st.text_input("链接URL", placeholder="https://...")
                link_desc = st.text_area("链接描述", height=100)
                link_image = st.file_uploader("上传展示图片", type=["jpg", "jpeg", "png"])
                image_path = None
                if link_image:
                    img_bytes = link_image.read()
                    image_path = RESOURCE_DIR / f"link_{int(time.time())}.png"
                    with open(image_path, "wb") as f:
                        f.write(img_bytes)
                    image_path = str(image_path)
            if st.button("💾 添加链接", use_container_width=True):
                if link_title and link_url:
                    if link_url.startswith(('http://', 'https://')):
                        link_id = save_resource_link(link_title, link_type, link_url, link_desc, image_path)
                        if link_id:
                            st.success(f"✅ 链接已添加 (ID: {link_id})")
                            st.rerun()
                    else:
                        st.error("请输入有效的URL（以http://或https://开头）")
                else:
                    st.warning("请填写链接标题和URL")
        # 筛选链接
        col_filter1, col_filter2 = st.columns([1, 3])
        with col_filter1:
            link_filter = st.selectbox("筛选链接类型", ["所有", "教科书", "教学课程", "教学直播", "其他"])

        # 显示链接列表
        links = get_resource_links(link_filter)
        st.markdown(f"#### 📋 资源链接列表 ({len(links)} 个)")

        if not links:
            st.info("暂无资源链接，请添加一些外部教学资源链接。")
        else:
            for link in links:
                link_id, title, link_type, url, description, image_path, created_at = link
                with st.container():
                    st.markdown('<div class="link-item">', unsafe_allow_html=True)

                    col_link1, col_link2 = st.columns([4, 1])
                    with col_link1:
                        st.markdown(f"### 📎 {title}")
                        st.markdown(f"**类型:** {link_type} | **创建时间:** {created_at}")
                        if description:
                            st.markdown(f"**描述:** {description}")
                        st.markdown(f"**链接:** [{url}]({url})")
                        if image_path and Path(image_path).exists():
                            st.image(image_path, width=120)
                    with col_link2:
                        if st.button("🗑️", key=f"del_link_{link_id}", help="删除链接"):
                            delete_resource_link(link_id)
                            st.success("链接已删除")
                            st.rerun()

                    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

def page_data_statistics():
    """数据统计页面"""
    st.markdown("---")
    st.markdown("### 📊 系统数据统计仪表盘")

    # 添加刷新按钮
    col_refresh, col_space = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 刷新统计数据", use_container_width=True):
            st.rerun()

    total, by_type, by_category, logs = get_db_stats()

    st.metric("总资源数", total)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 按资源类型分布")
        if by_type:
            df_type = pd.DataFrame.from_dict(by_type, orient='index', columns=['数量'])
            st.bar_chart(df_type)
            st.write("**详细数据:**")
            for resource_type, count in by_type.items():
                st.write(f"- {resource_type}: {count}")
        else:
            st.info("暂无资源类型数据")

    with col2:
        st.markdown("#### 按学科领域分布")
        if by_category:
            df_category = pd.DataFrame.from_dict(by_category, orient='index', columns=['数量'])
            st.bar_chart(df_category)
            st.write("**详细数据:**")
            for category, count in by_category.items():
                st.write(f"- {category}: {count}")
        else:
            st.info("暂无学科领域数据")

    st.markdown("---")
    st.markdown("#### 📝 最近10条操作日志")
    if logs:
        log_df = pd.DataFrame(logs, columns=['操作', '详情', '时间'])
        st.dataframe(log_df, use_container_width=True)
    else:
        st.info("暂无操作日志记录")

    # 数据库详细信息
    with st.expander("🔧 数据库详细信息"):
        st.write(f"**数据库文件路径:** {DB_FILE}")
        st.write(f"**数据库文件存在:** {os.path.exists(DB_FILE)}")
        if os.path.exists(DB_FILE):
            st.write(f"**数据库文件大小:** {os.path.getsize(DB_FILE)} 字节")

        # 检查数据库状态
        db_ok, db_msg = check_database_status()
        if db_ok:
            st.success(f"✅ {db_msg}")
        else:
            st.error(f"❌ {db_msg}")

    st.markdown('</div>', unsafe_allow_html=True)

def page_chat_interaction():
    """对话互动模块，可切换老师/学生角色"""
    st.markdown("---")
    st.markdown("### 💬 教学对话互动")

    # 角色选择
        # ...existing code...
    role = st.radio("选择你的身份", ["老师", "学生"], horizontal=True, key="chat_role")
    # 让AI扮演相反角色
    ai_role = "学生" if role == "老师" else "老师"
    
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 展示历史对话
    for msg in st.session_state.chat_history:
        who, text = msg["role"], msg["content"]
        st.chat_message("assistant" if who == "AI" else "user").write(f"**{who}：** {text}")

    # 输入框
    user_input = st.text_input("请输入你的对话内容", key="chat_input")
    use_kb = st.checkbox("结合知识库辅助回答（维基百科+本地资源）", value=True)
    if st.button("发送", use_container_width=True):
        if user_input.strip():
            kb_text = ""
            if use_kb:
                local_kb = search_local_resources(user_input)
                wiki_kb = search_wikipedia(user_input)
                if local_kb:
                    kb_text += f"本地资源相关内容：\n{local_kb}\n"
                if wiki_kb:
                    kb_text += f"维基百科相关内容：\n{wiki_kb}\n"
            st.session_state.chat_history.append({"role": role, "content": user_input})
            messages = [{"role": "system", "content": f"你现在扮演一名{ai_role}，请用{ai_role}的身份与对方对话。"}]
            for msg in st.session_state.chat_history:
                messages.append({"role": "user", "content": f"{msg['role']}：{msg['content']}"})
            # 加入知识库内容
            if kb_text:
                messages.append({"role": "system", "content": f"以下是知识库检索到的相关内容，可用于辅助回答：\n{kb_text}"})
            try:
                response = client.chat.completions.create(
                    model=st.session_state.openai_model,
                    messages=messages
                )
                ai_reply = response.choices[0].message.content
                st.session_state.chat_history.append({"role": "AI", "content": ai_reply})
                st.rerun()
            except Exception as e:
                st.error(f"对话生成失败: {e}")

    st.markdown('</div>', unsafe_allow_html=True)

def page_system_settings():
    """系统设置页面"""
    st.markdown("---")
    st.markdown("### ⚙️ 系统设置")
    
    st.selectbox(
        "选择AI模型",
        ["qwen-plus", "qwen2.5-7b-instruct-1m", "gpt-4", "gpt-4o"],
        key="openai_model",
        help="选择用于内容生成的AI模型"
    )

    st.info("API密钥已从环境变量加载，无需在此处填写。")
    st.markdown("---")

    # 数据库状态检查
    st.markdown("#### 🔧 系统状态")
    if st.button("🔍 检查数据库状态", use_container_width=True):
        db_ok, db_msg = check_database_status()
        if db_ok:
            st.success(f"✅ {db_msg}")
        else:
            st.error(f"❌ {db_msg}")

            # 尝试重新初始化数据库
            if st.button("🔧 尝试修复数据库"):
                if init_database():
                    st.success("数据库修复成功！")
                    st.rerun()
                else:
                    st.error("数据库修复失败，请检查文件权限。")

    # 数据库管理
    st.markdown("#### 📊 数据库管理")
    col_db1, col_db2 = st.columns(2)
    with col_db1:
        if st.button("📋 导出数据", use_container_width=True):
            # 导出资源数据
            resources = get_resources_from_db()
            if resources:
                df = pd.DataFrame(resources,
                                  columns=['ID', '标题', '类型', '分类', '创建时间', '描述', '文件路径', '内容'])
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="💾 下载资源数据CSV",
                    data=csv,
                    file_name=f"resources_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("没有数据可以导出")

    with col_db2:
        if st.button("🧹 清理日志", use_container_width=True):
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM user_logs WHERE timestamp < datetime('now', '-30 days')")
                    deleted_count = cursor.rowcount
                    conn.commit()
                st.success(f"已清理 {deleted_count} 条30天前的日志记录")
                log_action("CLEAN_LOGS", None, f"Cleaned {deleted_count} old log entries")
            except Exception as e:
                st.error(f"清理日志失败: {e}")

    st.markdown("---")
    st.markdown("#### 关于系统")
    st.write("本项目旨在构建一个基于多模态大模型的数字化教学资源制作系统，以满足比赛要求。")
    st.write("核心技术: Streamlit, OpenAI API, gTTS, SpeechRecognition, FPDF, SQLite.")
    st.write("版本: 2.1 (修复版) - 修复了数据库保存和日志记录问题，增强了错误处理和用户反馈")

    st.markdown('</div>', unsafe_allow_html=True)

# 学习内容
def page_student_content():
    """内容生成页面"""

    with st.container():
        st.markdown("---")
        st.markdown("### 🎯 知识属性")

        col1_2, col1_3 = st.columns([1,1])

        with col1_2:
            subject = st.selectbox("学科领域", ["语文", "数学", "英语", "物理", "化学", "生物", "自然科学"],
                                   help="选择相关学科领域")
        with col1_3:
            edu_level = st.selectbox("教育水平", ["小学", "初中", "高中"], help="选择目标教育水平")

        content_detail = st.text_area("选择内容类型", placeholder="例如: 请详细说出曹冲称象的历史典故", height=150)

    st.markdown("---")

    # 把按钮放在最后
    generate_content = st.button("🚀 生成知识讲解内容", use_container_width=True)

    if generate_content:
        with st.spinner("🤖 AI大脑正在思考并生成内容..."):
            try:
                # 构建提示
                prompt_template = """
                                你是一位经验丰富的{edu_level}{subject}教师，现在要为一位{edu_level}学生讲解以下知识点：
                                {user_input}

                                请按照以下要求进行讲解：
                                1. 内容要清晰易懂，符合{edu_level}学生的认知水平
                                2. 结构清晰，分为背景介绍、核心概念、实际应用、总结思考四部分
                                3. 使用生动的例子和类比帮助学生理解
                                4. 适当添加有趣的事实或故事增加吸引力
                                5. 使用Markdown格式，包含适当的标题和分段
                                """
                final_prompt = prompt_template.format(
                    user_input=content_detail,
                    subject=subject,
                    edu_level=edu_level
                )

                messages = [{"role": "system", "content": "你是一位专业的教育内容生成专家，擅长创建各种类型的教学资源。"},
                            {"role": "user", "content": final_prompt}]

                # (这是一个简化的RAG/Agent思想) 如果有图片，加入图片信息

                response = client.chat.completions.create(
                    model=st.session_state.openai_model,
                    messages=messages,
                    temperature=0.7,  # 适当创造性
                    max_tokens=1500  # 确保内容足够详细
                )
                # 添加成功提示
                st.toast("✅ 知识讲解内容已生成！", icon="✅")

                st.session_state.generated_stu_content = response.choices[0].message.content
            except Exception as e:
                st.error(f"内容生成失败: {e}")
                st.session_state.generated_stu_content = ""

    st.markdown('</div>', unsafe_allow_html=True)

    if "generated_stu_content" not in st.session_state:
        st.session_state.generated_stu_content = ""

    # 先显示生成结果
    if st.session_state.generated_stu_content:
        st.markdown("---")
        st.markdown("### 📝 内容生成区")

        st.markdown("#### ✨ 生成结果")
        st.markdown(st.session_state.generated_stu_content, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 🛠️ 后续操作")

        save_title = st.text_input("为该资源命名",
                                   value=f"{subject}_{datetime.datetime.now().strftime('%H%M')}")

        col_save1, col_save2 = st.columns(2)
        with col_save1:
            if st.button("💾 保存到资源库", use_container_width=True):
                if save_title:
                    res_id = save_resource_to_db(
                        title=save_title,
                        resource_type=edu_level,
                        category=subject,
                        content=st.session_state.generated_content,
                        description=content_detail[:1000]
                    )
                    st.success(f"✅ 已保存到资源库 (ID: {res_id})")
                    log_action("SAVE_CONTENT", res_id, save_title)
                else:
                    st.warning("请输入资源名称后再保存")
        with col_save2:
            pdf_bytes = None
            if st.button("📄 生成并下载PDF（默认命名与路径）", use_container_width=True):
                pdf_bytes = generate_pdf(st.session_state.generated_content, f"{save_title}.pdf")
            if pdf_bytes:
                st.download_button(
                    label="点击重命名和自定义路径",
                    data=pdf_bytes[0],  # 只传递pdf_bytes，不要传元组
                    file_name=f"{save_title}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

def page_student_practice():
    """学生自测练习页面"""

    # 初始化会话状态变量
    if "questions" not in st.session_state:
        st.session_state.questions = []
    if "user_answers" not in st.session_state:
        st.session_state.user_answers = {}
    if "submitted" not in st.session_state:
        st.session_state.submitted = False
    if "score" not in st.session_state:
        st.session_state.score = 0

    st.markdown("## 📝 自测练习")
    st.info("通过AI生成的练习题检验你的学习成果，系统会自动批改并给出详细解析")

    # 练习配置区域
    with st.expander("⚙️ 练习配置", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            subject = st.selectbox("学科领域",
                                   ["数学", "语文", "英语", "物理", "化学", "生物", "历史", "地理"],
                                   key="practice_subject")
        with col2:
            edu_level = st.selectbox("学习阶段",
                                     ["小学", "初中", "高中"],
                                     key="practice_level")
        with col3:
            question_count = st.slider("题目数量", 3, 20, 10, key="question_count")

        topic = st.text_input("练习主题（可选）",
                              placeholder="例如: 一元二次方程、文言文虚词用法、英语时态等",
                              key="practice_topic")

        if st.button("✨ 生成练习题", use_container_width=True):
            generate_questions(subject, edu_level, question_count, topic)
            st.session_state.submitted = False
            st.session_state.user_answers = {}
            st.session_state.score = 0
            st.toast(f"已生成{question_count}道{subject}练习题", icon="✅")

    st.markdown("---")

    # 显示练习题目
    if st.session_state.questions:
        st.markdown(f"### 📚 {subject}练习题 ({edu_level}阶段)")

        # 显示答题进度
        answered_count = sum(1 for i in range(len(st.session_state.questions))
                             if st.session_state.user_answers.get(i) is not None)
        progress = answered_count / len(st.session_state.questions)
        st.progress(progress, text=f"答题进度: {answered_count}/{len(st.session_state.questions)}")

        # 显示题目
        for idx, question in enumerate(st.session_state.questions):
            st.markdown(f"#### 题目 {idx + 1}")
            st.markdown(f"**{question['question']}**")

            # 根据题型显示不同答题方式
            if question["type"] == "选择题":
                options = question["options"]
                answer_key = f"answer_{idx}"

                # 显示选项
                if not st.session_state.submitted:
                    user_answer = st.radio(
                        "请选择答案:",
                        options,
                        key=answer_key,
                        index=None,
                        horizontal=True
                    )
                    st.session_state.user_answers[idx] = user_answer
                else:
                    user_answer = st.session_state.user_answers.get(idx)

                    # 提取用户选择的选项字母
                    user_choice = user_answer.strip()[0] if user_answer else ""

                    # 提取正确答案的选项字母
                    correct_choice = question["answer"].strip()[0] if question["answer"] else ""

                    # 显示结果
                    if user_choice.lower() == correct_choice.lower():
                        st.success(f"✓ 你的答案: {user_answer} (正确)")
                    else:
                        st.error(f"✗ 你的答案: {user_answer}")
                        st.success(f"正确答案: {question['answer']}")

            elif question["type"] == "填空题":
                answer_key = f"answer_{idx}"

                if not st.session_state.submitted:
                    user_answer = st.text_input(
                        "请在下方填写答案:",
                        key=answer_key,
                        placeholder="在此输入你的答案"
                    )
                    st.session_state.user_answers[idx] = user_answer
                else:
                    user_answer = st.session_state.user_answers.get(idx)

                    # 判断填空题答案（支持多个正确答案）
                    correct_answers = [ans.strip().lower() for ans in question["answer"].split("|")]
                    user_ans = user_answer.strip().lower() if user_answer else ""

                    if user_ans in correct_answers:
                        st.success(f"✓ 你的答案: {user_answer} (正确)")
                    else:
                        st.error(f"✗ 你的答案: {user_answer or '未填写'}")
                        st.success(f"正确答案: {question['answer'].replace('|', ' 或 ')}")

            # 显示解析（提交后显示）
            if st.session_state.submitted:
                with st.expander("查看解析", expanded=False):
                    st.markdown(f"**解析:** {question['explanation']}")

            st.markdown("---")

        # 提交按钮
        if not st.session_state.submitted:
            if st.button("📤 提交答案", type="primary", use_container_width=True):
                st.session_state.submitted = True
                calculate_score()
                st.rerun()

    # 显示成绩报告
    if st.session_state.submitted and st.session_state.questions:
        display_score_report()

    # # 没有题目时的提示
    # elif not st.session_state.questions:
    #     st.markdown("""
    #     <div class="practice-prompt">
    #         <div style="text-align:center; padding:2rem;">
    #             <h3>📝 自测练习使用指南</h3>
    #             <p>1. 选择学科和学习阶段</p>
    #             <p>2. 设置题目数量和主题（可选）</p>
    #             <p>3. 点击"生成练习题"按钮</p>
    #             <p>4. 完成所有题目后提交答案</p>
    #             <p>5. 查看成绩报告和题目解析</p>
    #         </div>
    #     </div>
    #     """, unsafe_allow_html=True)

def generate_questions(subject, edu_level, count, topic=""):
    """生成练习题"""
    try:
        # 构建提示词
        prompt = f"""
        你是一位经验丰富的{edu_level}{subject}教师，需要为{edu_level}学生创建{count}道练习题。
        {"练习主题是: " + topic if topic else ""}

        要求:
        1. 题目类型包括选择题和填空题，比例约为7:3
        2. 题目难度适中，符合{edu_level}学生的认知水平
        3. 每道题都要有详细的解析
        4. 对于选择题，提供4个选项，其中只有一个是正确答案
        5. 对于填空题，确保答案简洁明确，如有多个可能答案用|分隔
        6. 输出格式为JSON列表，每个题目包含以下字段:
           - "question": 题目文本
           - "type": "选择题" 或 "填空题"
           - "options": 仅选择题有，选项列表 (如: ["A. 选项1", "B. 选项2", ...])
           - "answer": 正确答案 (选择题用选项字母如"A"，填空题用答案文本)
           - "explanation": 题目解析

        示例格式:
        [
          {{
            "question": "问题文本",
            "type": "选择题",
            "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
            "answer": "B",
            "explanation": "解析文本"
          }},
          {{
            "question": "问题文本",
            "type": "填空题",
            "answer": "答案文本",
            "explanation": "解析文本"
          }}
        ]

        请直接输出JSON格式的题目列表，不要包含其他内容。
        """

        # 调用AI生成题目
        response = client.chat.completions.create(
            model=st.session_state.openai_model,
            messages=[
                {"role": "system", "content": "你是一位专业的教育专家，擅长设计各种学科的练习题"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        # 解析生成的JSON
        questions_json = response.choices[0].message.content
        st.session_state.questions = json.loads(questions_json)

        # 验证题目格式
        for q in st.session_state.questions:
            if q["type"] == "选择题":
                if not q.get("options") or len(q["options"]) != 4:
                    raise ValueError("选择题选项数量不正确")

    except json.JSONDecodeError:
        st.error("题目解析失败，请重试")
        st.session_state.questions = []
    except Exception as e:
        st.error(f"题目生成失败: {e}")
        st.session_state.questions = []

def calculate_score():
    """计算得分 - 修复版本"""
    total = len(st.session_state.questions)
    correct = 0

    for idx, question in enumerate(st.session_state.questions):
        user_answer = st.session_state.user_answers.get(idx)

        if not user_answer:
            continue  # 跳过未回答的题目

        if question["type"] == "选择题":
            # 提取用户选择的选项字母（第一个非空格字符）
            user_choice = user_answer.strip()[0] if user_answer else ""

            # 提取正确答案的选项字母
            correct_answer = question["answer"].strip()[0] if question["answer"] else ""

            # 比较选项字母（不区分大小写）
            if user_choice.lower() == correct_answer.lower():
                correct += 1

        elif question["type"] == "填空题":
            # 处理填空题的逻辑保持不变
            correct_answers = [ans.strip().lower() for ans in question["answer"].split("|")]
            user_ans = user_answer.strip().lower() if user_answer else ""
            if user_ans in correct_answers:
                correct += 1

    st.session_state.score = int(correct / total * 100) if total > 0 else 0

def display_score_report():
    """显示成绩报告"""
    total = len(st.session_state.questions)
    correct = int(total * st.session_state.score / 100)

    st.markdown("## 📊 成绩报告")

    # 成绩卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总题数", total)
    with col2:
        st.metric("答对题数", correct)
    with col3:
        st.metric("得分", f"{st.session_state.score}分")

    # 成绩评价
    if st.session_state.score >= 90:
        st.success("🎉 优秀！你的掌握情况非常好，继续保持！")
    elif st.session_state.score >= 70:
        st.info("👍 良好！你对知识点有较好的理解，但还有提升空间")
    elif st.session_state.score >= 60:
        st.warning("💪 及格！建议复习错题，加强薄弱环节")
    else:
        st.error("📚 需要努力！建议重新学习相关知识点")

    # 知识点掌握分析
    st.markdown("### 📌 知识点掌握分析")

    # 错题复习建议
    if st.session_state.score < 100:
        st.markdown("### 🔍 错题复习建议")
        st.write("以下是建议你重点复习的知识点：")

        # 收集错题知识点
        weak_topics = set()
        for idx, question in enumerate(st.session_state.questions):
            if not st.session_state.user_answers.get(idx):
                continue

            # 选择题判断
            if question["type"] == "选择题":
                if not st.session_state.user_answers[idx].startswith(question["answer"]):
                    weak_topics.add(extract_topic_from_question(question["question"]))

            # 填空题判断
            elif question["type"] == "填空题":
                correct_answers = [ans.strip().lower() for ans in question["answer"].split("|")]
                user_ans = st.session_state.user_answers[idx].strip().lower() if st.session_state.user_answers.get(
                    idx) else ""
                if user_ans not in correct_answers:
                    weak_topics.add(extract_topic_from_question(question["question"]))

        # 显示复习建议
        if weak_topics:
            st.write("建议重点复习以下知识点：")
            for topic in weak_topics:
                st.markdown(f"- {topic}")
        else:
            st.info("没有需要特别复习的知识点")

    # 重新练习按钮
    st.markdown("---")
    if st.button("🔄 重新生成练习题", use_container_width=True):
        st.session_state.submitted = False
        st.session_state.questions = []
        st.session_state.user_answers = {}
        st.session_state.score = 0
        st.rerun()

def extract_topic_from_question(question):
    """从问题中提取知识点"""
    try:
        response = client.chat.completions.create(
            model=st.session_state.openai_model,
            messages=[
                {"role": "system", "content": "你是一位教育专家，擅长分析题目中的知识点"},
                {"role": "user", "content": f"请从以下题目中提取核心知识点(不超过5个字): {question}"}
            ],
            temperature=0.1,
            max_tokens=20
        )
        return response.choices[0].message.content.strip()
    except:
        return "相关知识点"


import graphviz
import json
from collections import defaultdict

def page_personalized_learning():
    """个性化学习路径页面"""

    # 初始化会话状态
    if "learning_path" not in st.session_state:
        st.session_state.learning_path = []
    if "knowledge_graph" not in st.session_state:
        st.session_state.knowledge_graph = {"nodes": [], "edges": []}
    if "current_topic" not in st.session_state:
        st.session_state.current_topic = ""

    st.markdown("## 🧭 个性化学习路径")
    st.info("输入你想学习的主题，AI将为你规划最佳学习路径并展示知识图谱")

    # 学习主题输入
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            topic = st.text_input(
                "输入学习主题",
                placeholder="例如: 机器学习基础、中国古代史、量子力学入门等",
                key="learning_topic"
            )
        with col2:
            st.markdown("")
            st.markdown("")
            generate_path = st.button("🚀 生成学习路径", use_container_width=True)

    # 难度选择
    difficulty = st.select_slider(
        "选择学习难度",
        options=["入门", "基础", "中等", "进阶", "专家"],
        value="基础"
    )

    # 生成学习路径
    if generate_path and topic.strip():
        st.session_state.current_topic = topic
        with st.spinner("🤖 AI正在规划你的专属学习路径..."):
            try:
                generate_learning_path(topic, difficulty)
                st.toast("✅ 学习路径生成完成！", icon="✅")
            except Exception as e:
                st.error(f"路径生成失败: {e}")

    st.markdown("---")

    # 显示学习路径
    if st.session_state.learning_path:
        display_learning_path()

    # 显示知识图谱
    if st.session_state.knowledge_graph["nodes"]:
        display_knowledge_graph()

    # 没有主题时的提示
    elif not st.session_state.current_topic:
        st.markdown("""
        <div class="learning-prompt">
            <div style="text-align:center; padding:2rem;">
                <h3>📚 个性化学习指南</h3>
                <p>1. 在输入框中填写你想学习的主题</p>
                <p>2. 调整难度滑块匹配你的当前水平</p>
                <p>3. 点击"生成学习路径"按钮</p>
                <p>4. 查看AI规划的学习路径和知识图谱</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def search_wikipedia(query, lang="zh"):
    """从维基百科检索知识"""
    try:
        wikipedia.set_lang(lang)
        summary = wikipedia.summary(query, sentences=3, auto_suggest=False)
        return summary
    except Exception as e:
        return ""

def search_local_resources(query):
    """从本地资源库检索相关内容"""
    results = get_resources_from_db(search_term=query)
    if not results:
        return ""
    texts = []
    for res in results[:3]:
        title, content = res[1], res[7]
        if content:
            texts.append(f"【{title}】{content[:300]}")
    return "\n".join(texts)

def generate_learning_path(topic, difficulty):
    """生成个性化学习路径"""
    try:
        # 构建提示词
        prompt = f"""
        你是一位经验丰富的教育专家，需要为一位学生规划"学习主题"的学习路径。
        学生当前水平: {difficulty}级别
           - 阶段标题
           - 学习目标 (50字以上)
           - 核心知识点 (3-5个关键概念)
           - 建议学习资源 (2-3个真实可靠的资源，例如图书，网址等等)
           - 预计学习时间
        3. 构建知识图谱，包含:
           - 节点: 每个核心知识点
           - 边: 知识点之间的逻辑关系
        4. 输出格式为JSON，包含两个部分:
           - "path": 学习路径列表
           - "graph": 知识图谱 (包含"nodes"和"edges")

        知识图谱节点格式示例:
           {{"id": "概念1", "label": "概念名称", "group": "所属领域"}}
        知识图谱边格式示例:
           {{"source": "概念1", "target": "概念2", "label": "关系描述"}}

        示例结构:
        {{
          "path": [
            {{
              "title": "阶段标题",
              "goal": "阶段学习目标",
              "concepts": ["概念1", "概念2", "概念3"],
              "resources": ["资源1", "资源2"],
              "duration": "2小时"
            }}
          ],
          "graph": {{
            "nodes": [
              {{"id": "概念1", "label": "概念名称", "group": "领域"}},
              {{"id": "概念2", "label": "概念名称", "group": "领域"}}
            ],
            "edges": [
              {{"source": "概念1", "target": "概念2", "label": "基础关系"}}
            ]
          }}
        }}

        请直接输出JSON格式内容，不要包含其他任何文本。
        """

        # 调用AI生成学习路径
        response = client.chat.completions.create(
            model=st.session_state.openai_model,
            messages=[
                {"role": "system", "content": "你是一位专业的教育规划专家，擅长设计个性化学习路径"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )

        # 解析生成的JSON
        learning_data = json.loads(response.choices[0].message.content)

        # 保存到会话状态
        st.session_state.learning_path = learning_data.get("path", [])
        st.session_state.knowledge_graph = learning_data.get("graph", {"nodes": [], "edges": []})

    except json.JSONDecodeError:
        st.error("学习路径解析失败，请重试")
        st.session_state.learning_path = []
        st.session_state.knowledge_graph = {"nodes": [], "edges": []}
    except Exception as e:
        st.error(f"学习路径生成失败: {e}")
        st.session_state.learning_path = []
        st.session_state.knowledge_graph = {"nodes": [], "edges": []}

def display_learning_path():
    """显示学习路径"""
    st.markdown(f"### 📖 {st.session_state.current_topic} 学习路径")

    # 创建时间线展示
    for i, stage in enumerate(st.session_state.learning_path):
        with st.container():
            col1, col2 = st.columns([1, 10])

            with col1:
                # 阶段编号
                st.markdown(f"""
                <div style="
                    background-color: #4CAF50;
                    color: white;
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 18px;
                ">{i + 1}</div>
                """, unsafe_allow_html=True)

                # 时间标签
                st.caption(f"⏱️ {stage.get('duration', '')}")

            with col2:
                # 阶段内容
                st.markdown(f"#### {stage.get('title', '')}")
                st.markdown(f"**学习目标:** {stage.get('goal', '')}")

                # 知识点展示
                st.markdown("**核心知识点:**")
                for concept in stage.get('concepts', []):
                    st.markdown(f"- {concept}")

                # 学习资源
                with st.expander("💡 学习资源建议", expanded=False):
                    for resource in stage.get('resources', []):
                        st.markdown(f"- {resource}")

        # 阶段之间的分隔线（除了最后一个）
        if i < len(st.session_state.learning_path) - 1:
            st.markdown('<div style="height: 2=10px; border-left: 1px dashed #4CAF50; margin-left: 10px;"></div>',
                        unsafe_allow_html=True)

    st.markdown("---")

def display_knowledge_graph():
    """显示知识图谱"""
    st.markdown(f"### 🧠 {st.session_state.current_topic} 知识图谱")

    # 创建选项卡视图
    tab1, tab2 = st.tabs(["可视化图谱", "结构化视图"])

    with tab1:
        # 使用graphviz创建知识图谱
        graph = graphviz.Digraph(st.session_state.current_topic,
                                 graph_attr={"rankdir": "LR", "bgcolor": "transparent"})

        # 按组分类节点
        groups = defaultdict(list)
        for node in st.session_state.knowledge_graph["nodes"]:
            groups[node.get("group", "default")].append(node["id"])

        for group_name, nodes in groups.items():
            with graph.subgraph(name=f"cluster_{group_name}") as c:
                c.attr(style="filled",
                       color="lightgray",
                       label=group_name)
                for node_id in nodes:
                    c.node(node_id)

        # 添加边
        for edge in st.session_state.knowledge_graph["edges"]:
            graph.edge(edge["source"], edge["target"], label=edge.get("label", ""))

        # 在Streamlit中显示
        st.graphviz_chart(graph)

    with tab2:
        # 显示结构化知识图谱
        st.markdown("#### 知识点结构")

        # 创建知识网络图
        knowledge_map = {}
        for node in st.session_state.knowledge_graph["nodes"]:
            knowledge_map[node["id"]] = {
                "label": node["label"],
                "group": node.get("group", "其他"),
                "prerequisites": [],
                "leads_to": []
            }

        # 添加关系
        for edge in st.session_state.knowledge_graph["edges"]:
            if edge["source"] in knowledge_map and edge["target"] in knowledge_map:
                knowledge_map[edge["source"]]["leads_to"].append({
                    "target": edge["target"],
                    "relation": edge.get("label", "")
                })
                knowledge_map[edge["target"]]["prerequisites"].append({
                    "source": edge["source"],
                    "relation": edge.get("label", "")
                })

        # 按组展示知识点
        groups = defaultdict(list)
        for concept_id, concept_data in knowledge_map.items():
            groups[concept_data["group"]].append(concept_data)

        for group_name, concepts in groups.items():
            with st.expander(f"📚 {group_name} ({len(concepts)}个知识点)", expanded=True):
                for concept in concepts:
                    st.markdown(f"##### {concept['label']}")

                    # 显示前置知识
                    if concept["prerequisites"]:
                        st.markdown("**学习前提:**")
                        for pre in concept["prerequisites"]:
                            st.markdown(f"- {knowledge_map[pre['source']]['label']} ({pre['relation']})")

                    # 显示后续知识
                    if concept["leads_to"]:
                        st.markdown("**后续知识:**")
                        for lead in concept["leads_to"]:
                            st.markdown(f"- {knowledge_map[lead['target']]['label']} ({lead['relation']})")

                    st.markdown("---")

def page_stu_resource_management():
    """资源管理页面"""
    st.markdown("---")
    st.markdown("### 📚 教学资源管理中心")

    # 主要资源管理
    resource_tabs = st.tabs(["📁 资源库管理", "🔗 资源链接共享"])

    with resource_tabs[0]:
        # 筛选和搜索栏
        st.markdown("#### 筛选与搜索")
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_term = st.text_input("搜索资源（按标题、描述、标签）", label_visibility="collapsed",
                                        placeholder="输入关键词搜索...")
        with col2:
            # 从数据库动态获取分类和类型
            all_res = get_resources_from_db()
            categories = ["所有"] + sorted(list(set([r[3] for r in all_res])))
            types = ["所有"] + sorted(list(set([r[2] for r in all_res])))

            filter_category = st.selectbox("按学科筛选", options=categories, label_visibility="collapsed")
        with col3:
            filter_type = st.selectbox("按类型筛选", options=types, label_visibility="collapsed")

        # 刷新按钮
        if st.button("🔄 刷新资源列表", use_container_width=True):
            st.rerun()

        # 获取并显示资源
        resources = get_resources_from_db(search_term, filter_category, filter_type)
        st.markdown(f"--- \n#### 找到 {len(resources)} 个资源")

        if not resources:
            st.info("未找到匹配的资源。尝试调整筛选条件或创建新资源。")

            # 显示数据库状态
            with st.expander("🔧 数据库状态检查"):
                db_ok, db_msg = check_database_status()
                if db_ok:
                    st.success(db_msg)
                else:
                    st.error(db_msg)
        else:
            for res in resources:
                res_id, title, res_type, category, created_at, description, file_path, content = res
                with st.container():
                    st.markdown('<div class="resource-preview">', unsafe_allow_html=True)
                    col_title, col_button = st.columns([4, 1])
                    with col_title:
                        st.subheader(f"{title}")
                        st.caption(
                            f"ID: {res_id} | 类型: {res_type} | 学科: {category} | 创建于: {created_at.split('.')[0]}")

                    with col_button:
                        # 使用唯一key来避免Streamlit的按钮冲突
                        if st.button("🗑️ 删除", key=f"del_{res_id}", use_container_width=True):
                            try:
                                if delete_resource_from_db(res_id):
                                    st.success(f"资源 ID:{res_id} 已删除。")
                                    time.sleep(1)  # 给用户时间看到成功消息
                                    st.rerun()  # 刷新页面
                                else:
                                    st.error("删除失败")
                            except Exception as e:
                                st.error(f"删除失败: {e}")

                    with st.expander("查看详情/预览"):
                        if description:
                            st.markdown(f"**需求描述:** {description}")
                        if res_type in ["图像", "音频"] and file_path:
                            if Path(file_path).exists():
                                if res_type == "图像":
                                    st.image(str(file_path))
                                else:
                                    with open(file_path, "rb") as f:
                                        st.audio(f.read(), format="audio/mp3")
                            else:
                                st.warning("文件丢失或已被删除。")
                        elif content:
                            st.markdown(content)
                        else:
                            st.write("此资源无内容预览。")

                    st.markdown('</div>', unsafe_allow_html=True)
    with resource_tabs[1]:
        # 新增的资源链接管理功能
        st.markdown("#### 🔗 教学资源链接共享")
        st.markdown("管理教科书、教学课程、教学直播等外部资源链接")

        # 筛选链接
        col_filter1, col_filter2 = st.columns([1, 3])
        with col_filter1:
            link_filter = st.selectbox("筛选链接类型", ["所有", "教科书", "教学课程", "教学直播", "其他"])

        # 显示链接列表
        links = get_resource_links(link_filter)
        st.markdown(f"#### 📋 资源链接列表 ({len(links)} 个)")

        if not links:
            st.info("暂无资源链接，请添加一些外部教学资源链接。")
        else:
            for link in links:
                link_id, title, link_type, url, description, image_path, created_at = link
                with st.container():
                    st.markdown('<div class="link-item">', unsafe_allow_html=True)

                    col_link1, col_link2 = st.columns([4, 1])
                    with col_link1:
                        st.markdown(f"### 📎 {title}")
                        st.markdown(f"**类型:** {link_type} | **创建时间:** {created_at}")
                        if description:
                            st.markdown(f"**描述:** {description}")
                        st.markdown(f"**链接:** [{url}]({url})")
                        if image_path and Path(image_path).exists():
                            st.image(image_path, width=120)
                    with col_link2:
                        if st.button("🗑️", key=f"del_link_{link_id}", help="删除链接"):
                            delete_resource_link(link_id)
                            st.success("链接已删除")
                            st.rerun()

                    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# 将本地图片转换为base64
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        st.warning(f"背景图片未找到: {bin_file}")
        return ""
    except Exception as e:
        st.error(f"加载背景图片时出错: {e}")
        return ""


# 设置背景图片
def set_background(png_file="background.jpg"):
    bin_str = get_base64_of_bin_file(png_file)

    # 使用f-string格式化CSS，避免%格式化问题
    page_bg_img = f'''
    <style>
    .header-container {{
        background-image: url("data:image/png;base64,{bin_str}");
        background-size: cover;
        background-position: center;
        padding: 50px 20px;
        border-radius: 15px;
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin-bottom: 30px;
        position: relative;
    }}
    .header-overlay {{
        background-color: rgba(0, 0, 0, 0.4);
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        border-radius: 15px;
    }}
    .main-title {{
        color: white;
        font-size: 2.8rem !important;
        font-weight: bold;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        position: relative;
        z-index: 2;
        padding: 20px;
    }}
    </style>
    '''

    st.markdown(page_bg_img, unsafe_allow_html=True)


# --- 主函数 ---
def main():
    # 初始化
    init_database()
    load_custom_css()
    load_dotenv()
    load_sidebar_css()

    # 初始化数据库并检查状态
    try:
        if init_database():
            db_ok, db_msg = check_database_status()
            print(f"数据库初始化状态: {db_msg}")
        else:
            st.error("数据库初始化失败，请检查文件权限")
            st.stop()
    except Exception as e:
        st.error(f"数据库初始化异常: {e}")
        st.stop()


    # 加载API Key
    try:
        # 优先从环境变量加载，如果失败则使用你在代码中提供的硬编码key
        api_key = os.getenv("OPENAI_API_KEY", "sk-f6a020a664c64dd5a85e7e8317537619")
        base_url = os.getenv("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        global client
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        # 简单测试API连通性
        client.models.list()
        
        # st.markdown('<div class="success-message">✅ 系统已就绪！多模态AI引擎已激活</div>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"API配置或连接失败: {e}")
        st.stop()

    # 初始化session state
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = "qwen-turbo"

    # --- 页面标题 ---
    # 设置背景图片 - 确保图片在当前目录下
    set_background("background.jpg")  # 替换为你的本地图片文件名

    # 创建带背景图片的标题容器
    st.markdown(
        """
        <div class="header-container">
            <div class="header-overlay"></div>
            <div class="main-title">🏫 乡村教育AI智能系统</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    # st.markdown('<div class="main-title">🏫 乡村教育AI智能系统</div>', unsafe_allow_html=True)

    # 初始化状态
    if "active_module" not in st.session_state:
        st.session_state.active_module = "teacher"  # 默认教师模块
    if "teacher_page" not in st.session_state:
        st.session_state.teacher_page = "📝 内容生成"
    if "student_page" not in st.session_state:
        st.session_state.student_page = "📖 学习内容"

    # --- 侧边栏导航 ---
    with st.sidebar:

        st.markdown("### 🔄 模块切换")
        if st.button("切换至教师模块" if st.session_state.active_module == "student" else "切换至学生模块"):
            st.session_state.active_module = "teacher" if st.session_state.active_module == "student" else "student"

        st.markdown("---")

        if st.session_state.active_module == "teacher":
            st.markdown("## 👤 教师模块")
            teacher_page = st.radio(
                "教师功能",
                ["📝 教学内容生成", "🎨 多媒体制作",  "💬 对话互动", "📚 资源管理", "📊 数据统计", "⚙️ 系统设置"],
                label_visibility="collapsed",
                index=0,
                key="teacher_radio"
            )

            st.markdown("---")
        else:
            st.markdown("## 👨‍🎓 学生模块")
            student_page = st.radio(
                "学生功能",
                ["📖 知识讲解", "💬 对话互动", "🧠 自测练习", "🏆 个性化学习","🔍 学习资源搜索"],
                label_visibility="collapsed",
                index=0,
                key="student_radio"
            )

            st.markdown("---")
        st.info("本系统旨在为乡村教师与学生提供智能化、可视化的教育支持。")

        # 添加系统状态指示器
        with st.expander("📊 系统状态"):
            db_ok, db_msg = check_database_status()
            if db_ok:
                st.success("数据库: 正常")
            else:
                st.error("数据库: 异常")

            try:
                total_resources = get_db_stats()[0]
                st.metric("总资源数", total_resources)
            except:
                st.metric("总资源数", "N/A")
    # --- 页面路由 ---
    # 根据所选模块跳转（以教师模块为主）
    if st.session_state.active_module == "teacher":
        if teacher_page == "📝 教学内容生成":
            page_content_generation()
        elif teacher_page == "🎨 多媒体制作":
            page_multimedia_production()
        elif teacher_page == "💬 对话互动":
            page_chat_interaction()
        elif teacher_page == "📚 资源管理":
            page_resource_management()
        elif teacher_page == "📊 数据统计":
            page_data_statistics()
        elif teacher_page == "⚙️ 系统设置":
            page_system_settings()
    elif st.session_state.active_module == "student":
        if student_page == "📖 知识讲解":
            page_student_content()
        elif student_page == "💬 对话互动":
            page_chat_interaction()
        elif student_page == "🧠 自测练习":
            page_student_practice()
        elif student_page == "🏆 个性化学习":
            page_personalized_learning()
        elif student_page == "🔍 学习资源搜索":
            page_stu_resource_management()


if __name__ == "__main__":
    main()