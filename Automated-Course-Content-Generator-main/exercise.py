import streamlit as st
import openai
from dotenv import load_dotenv
import os
import json
import unicodedata
from fpdf import FPDF, HTMLMixin
import markdown

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

# --- Prompts (建议放在单独的prompts.py文件中) ---
# 为了方便你直接运行，我暂时把它们放在这里

PROMPT_TEMPLATES = {
    "课程大纲": """
    你是一位经验丰富的课程设计师。请根据以下要求，为一门课程设计一个详细、结构化的大纲。
    - 课程主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 大纲需要包含合理的模块划分，每个模块下有具体的章节或知识点。逻辑清晰，层层递进。请使用Markdown格式输出。
    """,
    "教学PPT": """
    你是一位PPT制作专家。请根据以下主题，生成一份教学PPT的核心内容大纲。
    - 主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 为每一页PPT提供标题和核心要点（3-5点）。内容应简洁、易于理解，并建议在何处使用图表或图像。总页数在10-15页之间。请使用Markdown格式输出。
    """,
    "练习题目": """
    你是一位资深的命题专家。请根据以下要求，设计一套练习题。
    - 知识点: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 生成5-10道题目，包含至少2种题型（如选择题、填空题、简答题）。题目需覆盖核心知识点，并附上标准答案和解析。请使用Markdown格式输出。
    """,
    "案例分析": """
    你是一位行业分析师和教育家。请根据以下场景，撰写一份教学案例分析。
    - 案例主题: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 案例需包含背景介绍、核心问题、分析过程和结论/启示。内容要具有深度和启发性。请使用Markdown格式输出。
    """,
    "实验指导": """
    你是一位实验室指导教师。请根据以下内容，编写一份清晰的实验指导手册。
    - 实验名称: {user_input}
    - 学科领域: {subject}
    - 目标学员水平: {edu_level}
    - 要求: 指导需包含实验目的、实验原理、所需器材、详细操作步骤、注意事项和数据记录表格。请使用Markdown格式输出。
    """
}

# --- 数据库初始化与操作 ---
DB_FILE = "teaching_resources.db"
RESOURCE_DIR = Path("resource_files")
RESOURCE_DIR.mkdir(exist_ok=True)

def init_database():
    """初始化SQLite数据库"""
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

def log_action(action, resource_id=None, details=""):
    """记录用户操作日志"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_logs (action, resource_id, details) VALUES (?, ?, ?)",
            (action, resource_id, details)
        )

def save_resource_to_db(title, resource_type, category, content=None, file_path=None, tags="", description=""):
    """保存资源到数据库"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO resources (title, type, category, content, file_path, tags, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, resource_type, category, content, str(file_path) if file_path else None, tags, description)
        )
        resource_id = cursor.lastrowid
        log_action("CREATE", resource_id, f"Created {resource_type}: {title}")
        return resource_id

def get_resources_from_db(search_term="", category=None, resource_type=None):
    """从数据库获取资源，支持搜索和筛选"""
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
        return cursor.execute(query, params).fetchall()

def delete_resource_from_db(resource_id):
    """从数据库删除资源并删除关联文件"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # 先获取文件路径
        cursor.execute("SELECT file_path, title, type FROM resources WHERE id = ?", (resource_id,))
        result = cursor.fetchone()
        if result and result[0]:
            file_to_delete = Path(result[0])
            if file_to_delete.exists():
                file_to_delete.unlink() # 删除文件
        
        # 删除数据库记录
        cursor.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        log_action("DELETE", resource_id, f"Deleted resource ID {resource_id} ({result[2]}: {result[1]})")

def get_db_stats():
    """获取数据库统计信息"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        total_resources = cursor.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        resources_by_type = cursor.execute("SELECT type, COUNT(*) FROM resources GROUP BY type").fetchall()
        resources_by_category = cursor.execute("SELECT category, COUNT(*) FROM resources GROUP BY category").fetchall()
        logs = cursor.execute("SELECT action, details, timestamp FROM user_logs ORDER BY timestamp DESC LIMIT 10").fetchall()
        return total_resources, dict(resources_by_type), dict(resources_by_category), logs

# --- 多模态与文件处理函数 ---

def generate_pdf(content, filename):
    """将Markdown内容渲染为PDF，保留样式"""
    pdf = MyFPDF()
    pdf.add_page()

    # 用绝对路径指定字体文件
    font_path = os.path.join(os.path.dirname(__file__), "simsun.ttf")
    try:
        pdf.add_font('simsun', '', font_path, uni=True)
        pdf.set_font('simsun', '', 12)
    except RuntimeError:
        st.warning("未找到中文字体 'simsun.ttf'，PDF中的中文可能无法正确显示。请下载并放置该字体文件到项目目录。")
        pdf.set_font('Arial', '', 12)

    # Markdown转HTML
    html = markdown.markdown(content)
    # 渲染HTML到PDF
    pdf.write_html(html)
    pdf_bytes = pdf.output(dest="S")
    with open(filename, 'wb') as f:
        f.write(pdf_bytes)
    return pdf_bytes

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

# --- UI & 页面渲染 ---

def load_custom_css():
    """加载自定义CSS样式（与你修改版一致）"""
    st.markdown("""
    <style>
    /* 全局样式 */
    .main { padding-top: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
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
    .success-message { background: linear-gradient(45deg, #28a745, #20c997); color: white; padding: 1rem; border-radius: 10px; margin: 1rem 0; text-align: center; animation: slideIn 0.5s ease-out; }
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
            subject = st.selectbox("学科领域", ["计算机科学", "数学", "物理", "化学", "生物", "经济学", "管理学", "语言文学", "其他"], help="选择相关学科领域")
            edu_level = st.selectbox("教育水平", ["小学", "初中", "高中", "大专", "本科", "研究生"], help="选择目标教育水平")
            
            st.markdown("---")
            st.markdown("### 🎤 多模态输入")
            input_method = st.radio("选择输入方式", ["文本输入", "语音输入", "图像输入"], horizontal=True, label_visibility="collapsed")
            
            user_input_text = ""
            user_input_image = None
            
            if input_method == "文本输入":
                user_input_text = st.text_area("请描述您的需求", placeholder=f"例如：为{subject}学科生成一个关于...的{content_type}", height=150)
            
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
                if user_input_image:
                    st.image(user_input_image, caption="上传的图像", use_column_width=True)
                user_input_text = st.text_area("请结合图像描述您的需求", placeholder="例如：基于上图，生成一个相关的案例分析...", height=100)
            
            generate_content = st.button("🚀 生成教学内容", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown("---")
        st.markdown("### 📝 内容生成区")
        
        if "generated_content" not in st.session_state:
            st.session_state.generated_content = ""

        if generate_content and user_input_text.strip():
            with st.spinner("🤖 AI正在思考并生成内容..."):
                try:
                    # 构建提示
                    prompt_template = PROMPT_TEMPLATES.get(content_type, "请根据以下信息生成内容：{user_input}")
                    final_prompt = prompt_template.format(user_input=user_input_text, subject=subject, edu_level=edu_level)
                    
                    messages = [{"role": "system", "content": "你是一位专业的教育内容生成专家，擅长创建各种类型的教学资源。"}]
                    
                    # (这是一个简化的RAG/Agent思想) 如果有图片，加入图片信息
                    if user_input_image:
                        messages.append({"role": "user", "content": f"[图像信息：用户上传了一张图片，并希望基于此进行创作] {final_prompt}"})
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

        if st.session_state.generated_content:
            st.markdown("#### ✨ 生成结果")
            st.markdown(st.session_state.generated_content)
            
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
                # 生成PDF并提供下载
                pdf_path = RESOURCE_DIR / f"{save_title.replace(' ', '_')}.pdf"
                pdf_bytes = generate_pdf(st.session_state.generated_content, str(pdf_path))
                st.download_button(
                    label="📄 下载PDF",
                    data=pdf_bytes,
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

        st.markdown('</div>', unsafe_allow_html=True)

def page_multimedia_production():
    """多媒体制作页面"""
    st.markdown('<div class="card-container">', unsafe_allow_html=True)
    st.markdown("### 🎨 多媒体资源制作中心")
    media_tabs = st.tabs(["🖼️ AI图像生成", "🎵 AI音频合成", "🎬 视频工具 (概念)", "� 图表制作 (概念)"])

    with media_tabs[0]: # AI图像生成
        st.markdown("#### 通过文本描述生成教学图像")
        col1, col2 = st.columns([1, 1])
        with col1:
            image_prompt = st.text_area("图像描述 (Prompt)", placeholder="例如：一个宇航员在火星表面插上旗帜，背景是地球，卡通风格", height=120)
            image_style = st.selectbox("图像风格", ["真实照片", "卡通插画", "像素艺术", "水彩画", "科技感"])
            if st.button("🎨 生成图像", use_container_width=True):
                if image_prompt.strip():
                    with st.spinner("DALL-E 3 正在创作中..."):
                        try:
                            full_prompt = f"{image_prompt}, style: {image_style}."
                            response = client.images.generate(
                                model="dall-e-3",
                                prompt=full_prompt,
                                size="1024x1024",
                                quality="standard",
                                n=1,
                            )
                            image_url = response.data[0].url
                            st.session_state.generated_image_url = image_url
                            st.session_state.generated_image_prompt = image_prompt
                        except Exception as e:
                            st.error(f"图像生成失败: {e}")
                            st.session_state.generated_image_url = None
                else:
                    st.warning("请输入图像描述")

        with col2:
            if "generated_image_url" in st.session_state and st.session_state.generated_image_url:
                st.image(st.session_state.generated_image_url, caption="AI生成图像")
                # 下载和保存
                image_data = requests.get(st.session_state.generated_image_url).content
                img_title = st.session_state.generated_image_prompt[:30].replace(" ", "_")
                file_path = RESOURCE_DIR / f"img_{img_title}.png"
                with open(file_path, "wb") as f:
                    f.write(image_data)
                
                st.download_button("📥 下载图像", image_data, file_name=f"{img_title}.png", use_container_width=True)
                if st.button("💾 保存至资源库", use_container_width=True):
                    res_id = save_resource_to_db(
                        title=f"AI图像: {img_title}",
                        resource_type="图像",
                        category="AI生成",
                        file_path=file_path,
                        description=st.session_state.generated_image_prompt
                    )
                    st.success(f"图像已保存到资源库 (ID: {res_id})")

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
        
    st.markdown('</div>', unsafe_allow_html=True)

def page_resource_management():
    """资源管理页面"""
    st.markdown('<div class="card-container">', unsafe_allow_html=True)
    st.markdown("### 📚 教学资源管理中心")
    
    # 筛选和搜索栏
    st.markdown("#### 筛选与搜索")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_term = st.text_input("搜索资源（按标题、描述、标签）", label_visibility="collapsed", placeholder="输入关键词搜索...")
    with col2:
        # 从数据库动态获取分类和类型
        all_res = get_resources_from_db()
        categories = ["所有"] + sorted(list(set([r[3] for r in all_res])))
        types = ["所有"] + sorted(list(set([r[2] for r in all_res])))
        
        filter_category = st.selectbox("按学科筛选", options=categories, label_visibility="collapsed")
    with col3:
        filter_type = st.selectbox("按类型筛选", options=types, label_visibility="collapsed")
    
    # 获取并显示资源
    resources = get_resources_from_db(search_term, filter_category, filter_type)
    st.markdown(f"--- \n#### 找到 {len(resources)} 个资源")

    if not resources:
        st.info("未找到匹配的资源。尝试调整筛选条件或创建新资源。")
    else:
        for res in resources:
            res_id, title, res_type, category, created_at, description, file_path, content = res
            with st.container():
                st.markdown('<div class="resource-preview">', unsafe_allow_html=True)
                col_title, col_button = st.columns([4, 1])
                with col_title:
                    st.subheader(f"{title}")
                    st.caption(f"ID: {res_id} | 类型: {res_type} | 学科: {category} | 创建于: {created_at.split('.')[0]}")
                
                with col_button:
                    # 使用唯一key来避免Streamlit的按钮冲突
                    if st.button("🗑️ 删除", key=f"del_{res_id}", use_container_width=True):
                        delete_resource_from_db(res_id)
                        st.success(f"资源 ID:{res_id} 已删除。")
                        st.experimental_rerun() # 刷新页面
                
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

    st.markdown('</div>', unsafe_allow_html=True)

def page_data_statistics():
    """数据统计页面"""
    st.markdown('<div class="card-container">', unsafe_allow_html=True)
    st.markdown("### 📊 系统数据统计仪表盘")
    
    total, by_type, by_category, logs = get_db_stats()

    st.metric("总资源数", total)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 按资源类型分布")
        if by_type:
            st.bar_chart(pd.DataFrame.from_dict(by_type, orient='index', columns=['数量']))
        else:
            st.info("暂无资源类型数据")
            
    with col2:
        st.markdown("#### 按学料领域分布")
        if by_category:
            st.bar_chart(pd.DataFrame.from_dict(by_category, orient='index', columns=['数量']))
        else:
            st.info("暂无学科领域数据")

    st.markdown("---")
    st.markdown("#### 📝 最近10条操作日志")
    log_df = pd.DataFrame(logs, columns=['操作', '详情', '时间'])
    st.dataframe(log_df, use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

def page_system_settings():
    """系统设置页面"""
    st.markdown('<div class="card-container">', unsafe_allow_html=True)
    st.markdown("### ⚙️ 系统设置")
    
    st.selectbox(
        "选择AI模型",
        ["gpt-3.5-turbo", "gpt-4", "gpt-4o"],
        key="openai_model",
        help="选择用于内容生成的AI模型"
    )

    st.info("API密钥已从环境变量加载，无需在此处填写。")
    st.markdown("---")
    st.markdown("#### 关于系统")
    st.write("本项目旨在构建一个基于多模态大模型的数字化教学资源制作系统，以满足比赛要求。")
    st.write("核心技术: Streamlit, OpenAI API, gTTS, SpeechRecognition, FPDF, SQLite.")

    st.markdown('</div>', unsafe_allow_html=True)

# --- 主函数 ---
def main():
    # 初始化
    init_database()
    load_custom_css()
    load_dotenv()

    # 页面配置
    st.set_page_config(
        page_title="数字化教学资源制作系统",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 加载API Key
    try:
        # 优先从环境变量加载，如果失败则使用你在代码中提供的硬编码key
        api_key = os.getenv("OPENAI_API_KEY", "sk-xlSmAXJRk8FraBrG26FcD8CfD725469cB70037A7D4Bf77Aa")
        base_url = os.getenv("OPENAI_API_BASE", "https://free.v36.cm/v1")
        
        global client
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        # 简单测试API连通性
        client.models.list()
        
        st.markdown('<div class="success-message">✅ 系统已就绪！多模态AI引擎已激活</div>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"API配置或连接失败: {e}")
        st.stop()

    # 初始化session state
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = "gpt-3.5-turbo"

    # --- 页面标题 ---
    st.markdown('<div class="main-title">🎓 数字化教学资源制作系统</div>', unsafe_allow_html=True)

    # --- 侧边栏导航 ---
    with st.sidebar:
        st.markdown("### 🎯 功能导航")
        page = st.radio(
            "选择功能模块",
            ["📝 内容生成", "🎨 多媒体制作", "📚 资源管理", "📊 数据统计", "⚙️ 系统设置"],
            label_visibility="collapsed"
        )
        st.markdown("---")
        st.info("本系统旨在为教师提供高效的教学资源创作工具。")

    # --- 页面路由 ---
    if page == "📝 内容生成":
        page_content_generation()
    elif page == "🎨 多媒体制作":
        page_multimedia_production()
    elif page == "📚 资源管理":
        page_resource_management()
    elif page == "📊 数据统计":
        page_data_statistics()
    elif page == "⚙️ 系统设置":
        page_system_settings()

if __name__ == "__main__":
    main()
