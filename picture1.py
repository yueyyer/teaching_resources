import streamlit as st
from word2picture import generate_picture_by_text
from pathlib import Path
import requests
import time
import os
import mimetypes
import json

# 讯飞API配置（请替换为你自己的）
APPID = 'b18dc113'
APIKEY = '20082c2448c81bcb4fa76a12c6be12fe'
APISECRET = 'NjRkNDk5MWUwNmU1MDg5Y2RjZjczOWM2'

# Tripo3D API Key（请替换为你的真实API Key）
TRIPO3D_API_KEY = 'tsk_sNdMKve3WQhbTa2jo3hI2ixm9UESLCHFMHZXzlygKXm'

SAVE_DIR = Path("generated_images")
SAVE_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="焕古觉今—“AI+”传统文化作品创作设计工具", page_icon="🖼️", layout="centered")

# 美化样式
st.markdown("""
    <style>
    /* Tab栏科技感渐变+发光 */
    .stTabs [data-baseweb="tab-list"] {
        background: linear-gradient(90deg, #232526 0%, #414345 100%);
        border-radius: 12px 12px 0 0;
        box-shadow: 0 2px 12px #00eaff44;
        padding: 0.5rem 0.5rem 0 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.15rem;
        font-weight: 700;
        color: #e6f7ff; /* 更亮的蓝白色 */
        letter-spacing: 1px;
        padding: 0.7rem 2.2rem;
        transition: color 0.2s;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #232526 0%, #00eaff 100%);
        color: #fff;
        border-radius: 12px 12px 0 0;
        border-bottom: 3px solid #00eaff;
        box-shadow: 0 4px 24px #00eaff55;
        text-shadow: 0 0 8px #00eaff99;
    }
    .stApp {
        background: linear-gradient(135deg, #232526 0%, #0f2027 100%);
        min-height: 100vh;
        color: #e6f7ff !important; /* 全局字体更亮 */
    }
    /* 标题科技感发光 */
    .st-emotion-cache-10trblm {
        color: #00eaff !important;
        text-shadow: 0 0 12px #00eaff99, 0 0 2px #fff;
        font-weight: 900;
        letter-spacing: 2px;
    }
    /* 按钮科技蓝色渐变+发光 */
    .stButton>button {
        background: linear-gradient(90deg, #00eaff 0%, #005bea 100%);
        color: #fff;
        border: none;
        border-radius: 8px;
        font-weight: 700;
        box-shadow: 0 2px 12px #00eaff44;
        transition: background 0.2s, box-shadow 0.2s;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #005bea 0%, #00eaff 100%);
        box-shadow: 0 4px 24px #00eaff99;
        color: #fff;
    }
    /* 输入框科技感 */
    .stTextInput>div>div>input, .stTextArea textarea {
        background: #232526;
        color: #e6f7ff; /* 更亮的输入字体 */
        border: 1.5px solid #00eaff55;
        border-radius: 6px;
    }
    .stTextInput>div>div>input:focus, .stTextArea textarea:focus {
        border: 2px solid #00eaff;
        box-shadow: 0 0 8px #00eaff99;
    }
    /* 卡片和提示 */
    .stAlert {
        background: linear-gradient(90deg, #232526 0%, #00eaff22 100%);
        border-left: 5px solid #00eaff;
        color: #fff;
    }
    </style>
""", unsafe_allow_html=True)

st.title("焕古觉今—“AI+”传统文化作品创作设计工具")
st.markdown("请选择上方的功能标签进入不同的AI生成页：")

tabs = st.tabs(["tab0 文生图", "tab1 文生3D模型", "tab2 图生3D模型"])

# tab0 文生图
with tabs[0]:
    st.header("✨ 文生图")
    desc = st.text_area("请输入图片描述", placeholder="例如：一只可爱的猫，坐在草地上", key="txt2img", height=100)
    if st.button("生成图片", key="btn_txt2img"):
        if desc.strip():
            with st.spinner("AI正在生成图片，请稍候..."):
                img_path = generate_picture_by_text(desc, APPID, APIKEY, APISECRET, save_dir=str(SAVE_DIR))
                if img_path and Path(img_path).exists():
                    st.success("图片生成成功！")
                    st.image(img_path, caption="AI生成图片", use_column_width=True)
                    with open(img_path, "rb") as f:
                        st.download_button("📥 下载图片", f, file_name=Path(img_path).name)
                else:
                    st.error("图片生成失败，请重试或检查API配置。")
        else:
            st.warning("请输入图片描述后再生成。")

# tab1 文生3D模型
with tabs[1]:
    st.header("🦾 文生3D模型")
    text_prompt = st.text_area("请输入3D模型描述", placeholder="例如：一只可爱的猫，坐在草地上", key="txt2model", height=100)
    if st.button("文本生成3D模型", key="btn_txt2model"):
        if not TRIPO3D_API_KEY or TRIPO3D_API_KEY == "YOUR_TRIPO_API_KEY":
            st.error("请先在代码中配置你的 Tripo3D API Key！")
        elif not text_prompt.strip():
            st.warning("请输入3D模型描述后再生成。")
        else:
            with st.spinner("3D模型任务提交中..."):
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {TRIPO3D_API_KEY}"
                }
                payload = {
                    "type": "text_to_model",
                    "prompt": text_prompt.strip()
                }
                try:
                    resp = requests.post(
                        "https://api.tripo3d.ai/v2/openapi/task",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    data = resp.json()
                    if data.get("code") == 0 and "data" in data and "task_id" in data["data"]:
                        task_id = data["data"]["task_id"]
                        st.success(f"任务已提交，Task ID: {task_id}")
                        # 轮询获取结果
                        with st.spinner("3D模型生成中，请耐心等待（通常1-2分钟）..."):
                            model_url = None
                            image_url = None
                            render_url = None
                            for _ in range(120):
                                poll = requests.get(
                                    f"https://api.tripo3d.ai/v2/openapi/task/{task_id}",
                                    headers=headers,
                                    timeout=30
                                )
                                poll_data = poll.json()
                                if poll_data.get("code") == 0 and "data" in poll_data:
                                    status = poll_data["data"].get("status")
                                    if status == "success":
                                        result = poll_data["data"].get("result", {})
                                        if "pbr_model" in result and isinstance(result["pbr_model"], dict):
                                            model_url = result["pbr_model"].get("url")
                                        if "rendered_image" in result and isinstance(result["rendered_image"], dict):
                                            render_url = result["rendered_image"].get("url")
                                        if "generated_image" in result:
                                            image_url = result["generated_image"]
                                        break
                                    elif status == "failed":
                                        st.error("3D模型生成失败！")
                                        break
                                time.sleep(5)
                            # 显示结果
                            if model_url:
                                st.success("3D模型生成成功！")
                                st.markdown(f"[点击下载3D模型文件（.glb）]({model_url})")
                                if render_url:
                                    st.image(render_url, caption="3D模型渲染图", use_column_width=True)
                                    render_img_bytes = requests.get(render_url).content
                                    st.download_button("下载3D模型渲染图", render_img_bytes, file_name="rendered_image.webp")
                                elif image_url:
                                    st.image(image_url, caption="AI生成图片", use_column_width=True)
                                    gen_img_bytes = requests.get(image_url).content
                                    st.download_button("下载中间渲染图", gen_img_bytes, file_name="generated_image.webp")
                            else:
                                st.warning("3D模型生成超时或未获取到模型文件，请稍后重试。")
                    else:
                        st.error(f"任务提交失败: {data.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"请求异常: {str(e)}")

# tab2 图生3D模型
with tabs[2]:
    st.header("🖼️ 图生3D模型")
    uploaded_file = st.file_uploader("上传图片（jpg/png/webp）", type=["jpg", "jpeg", "png", "webp"], key="file_uploader")
    if st.button("上传图片并生成3D模型", key="btn_img2model"):
        if not TRIPO3D_API_KEY or TRIPO3D_API_KEY == "YOUR_TRIPO_API_KEY":
            st.error("请先在代码中配置你的 Tripo3D API Key！")
        elif not uploaded_file:
            st.warning("请先上传图片文件。")
        else:
            try:
                with st.spinner("图片上传中..."):
                    mime_type, _ = mimetypes.guess_type(uploaded_file.name)
                    if not mime_type:
                        mime_type = "image/jpeg"
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), mime_type)}
                    headers = {"Authorization": f"Bearer {TRIPO3D_API_KEY}"}
                    resp = requests.post(
                        "https://api.tripo3d.ai/v2/openapi/upload/sts",
                        headers=headers,
                        files=files,
                        timeout=60
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("code") == 0 and "data" in data and "image_token" in data["data"]:
                        image_token = data["data"]["image_token"]
                        st.success(f"图片上传成功，image_token: {image_token}")
                        # 用 image_token 触发图片转3D任务
                        with st.spinner("3D模型任务提交中..."):
                            file_ext = uploaded_file.name.split('.')[-1].lower()
                            if file_ext == "jpeg":
                                file_ext = "jpg"
                            payload2 = {
                                "type": "image_to_model",
                                "file": {
                                    "type": file_ext,
                                    "file_token": image_token.strip()
                                }
                            }
                            headers2 = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {TRIPO3D_API_KEY}"
                            }
                            resp2 = requests.post(
                                "https://api.tripo3d.ai/v2/openapi/task",
                                headers=headers2,
                                json=payload2,
                                timeout=30
                            )
                            resp2.raise_for_status()
                            data2 = resp2.json()
                            if data2.get("code") == 0 and "data" in data2 and "task_id" in data2["data"]:
                                task_id = data2["data"]["task_id"]
                                st.success(f"3D模型任务已提交，Task ID: {task_id}")
                                # 轮询获取结果
                                with st.spinner("3D模型生成中，请耐心等待（通常1-2分钟）..."):
                                    model_url = None
                                    image_url = None
                                    render_url = None
                                    for _ in range(120):
                                        poll = requests.get(
                                            f"https://api.tripo3d.ai/v2/openapi/task/{task_id}",
                                            headers=headers2,
                                            timeout=30
                                        )
                                        poll.raise_for_status()
                                        poll_data = poll.json()
                                        if poll_data.get("code") == 0 and "data" in poll_data and poll_data["data"].get("status") == "success":
                                            result = poll_data["data"].get("result", {})
                                            model_url = None
                                            image_url = None
                                            render_url = None
                                            if "pbr_model" in result and isinstance(result["pbr_model"], dict):
                                                model_url = result["pbr_model"].get("url")
                                            if "rendered_image" in result and isinstance(result["rendered_image"], dict):
                                                render_url = result["rendered_image"].get("url")
                                            if "generated_image" in result:
                                                image_url = result["generated_image"]
                                            break
                                        elif poll_data.get("code") == 0 and poll_data["data"].get("status") == "failed":
                                            st.error("3D模型生成失败！")
                                            break
                                        time.sleep(5)
                                    if model_url:
                                        st.success("3D模型生成成功！")
                                        st.markdown(f"[点击下载3D模型文件（.glb）]({model_url})")
                                        if render_url:
                                            st.image(render_url, caption="3D模型渲染图", use_column_width=True)
                                            render_img_bytes = requests.get(render_url).content
                                            st.download_button("下载3D模型渲染图", render_img_bytes, file_name="rendered_image.webp")
                                        elif image_url:
                                            st.image(image_url, caption="AI生成图片", use_column_width=True)
                                            gen_img_bytes = requests.get(image_url).content
                                            st.download_button("下载中间渲染图", gen_img_bytes, file_name="generated_image.webp")
                                    else:
                                        st.warning("3D模型生成超时，请稍后重试。")
                            else:
                                st.error(f"3D任务提交失败: {data2}")
                    else:
                        st.error(f"图片上传失败: {data}")
            except Exception as e:
                st.error(f"图片上传或3D生成接口异常: {e}")