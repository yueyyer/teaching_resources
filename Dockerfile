FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 拷贝所有项目文件到容器中
COPY . /app

# 安装依赖
RUN pip install --upgrade pip \
    && pip install -r requirements.txt || true

# 设置容器启动后运行的命令
CMD ["python3", "exercise.py"]
