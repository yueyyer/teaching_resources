# encoding: UTF-8
import time
import os
import requests
from datetime import datetime
from wsgiref.handlers import format_date_time
from time import mktime
import hashlib
import base64
import hmac
from urllib.parse import urlencode
import json
from PIL import Image
from io import BytesIO

class AssembleHeaderException(Exception):
    def __init__(self, msg):
        self.message = msg


class Url:
    def __init__(this, host, path, schema):
        this.host = host
        this.path = path
        this.schema = schema
        pass


# calculate sha256 and encode to base64
def sha256base64(data):
    sha256 = hashlib.sha256()
    sha256.update(data)
    digest = base64.b64encode(sha256.digest()).decode(encoding='utf-8')
    return digest


def parse_url(requset_url):
    stidx = requset_url.index("://")
    host = requset_url[stidx + 3:]
    schema = requset_url[:stidx + 3]
    edidx = host.index("/")
    if edidx <= 0:
        raise AssembleHeaderException("invalid request url:" + requset_url)
    path = host[edidx:]
    host = host[:edidx]
    u = Url(host, path, schema)
    return u


# 生成鉴权url
def assemble_ws_auth_url(requset_url, method="GET", api_key="", api_secret=""):
    u = parse_url(requset_url)
    host = u.host
    path = u.path
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    signature_origin = "host: {}\ndate: {}\n{} {} HTTP/1.1".format(host, date, method, path)
    signature_sha = hmac.new(api_secret.encode('utf-8'), signature_origin.encode('utf-8'),
                             digestmod=hashlib.sha256).digest()
    signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
    authorization_origin = "api_key=\"%s\", algorithm=\"%s\", headers=\"%s\", signature=\"%s\"" % (
        api_key, "hmac-sha256", "host date request-line", signature_sha)
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    values = {
        "host": host,
        "date": date,
        "authorization": authorization
    }

    return requset_url + "?" + urlencode(values)

# 生成请求body体
def getBody(appid, text):
    body = {
        "header": {
            "app_id": appid,
            "uid": "123456789"
        },
        "parameter": {
            "chat": {
                "domain": "general",
                "temperature": 0.5,
                "max_tokens": 4096
            }
        },
        "payload": {
            "message": {
                "text": [
                    {
                        "role": "user",
                        "content": text
                    }
                ]
            }
        }
    }
    return body

# 发起请求并返回结果 - 修复参数顺序
def main(text, appid, apikey, apisecret):
    try:
        host = 'http://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti'
        url = assemble_ws_auth_url(host, method='POST', api_key=apikey, api_secret=apisecret)
        content = getBody(appid, text)
        response = requests.post(url, json=content, headers={'content-type': "application/json"}, timeout=30)
        return response.text
    except Exception as e:
        print(f"请求异常: {e}")
        return None

# 将base64的图片数据存在本地
def base64_to_image(base64_data, save_path):
    try:
        # 确保保存目录存在
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        # 解码base64数据
        img_data = base64.b64decode(base64_data)
        
        # 将解码后的数据转换为图片
        img = Image.open(BytesIO(img_data))
        
        # 保存图片到本地
        img.save(save_path)
        return True
    except Exception as e:
        print(f"图片保存失败: {e}")
        return False

# 主函数 - 修复参数顺序，与exercise.py中的调用保持一致
def generate_picture_by_text(text, appid, apikey, apisecret, save_dir="./"):
    try:
        res = main(text, appid, apikey, apisecret)
        if res:
            return parser_Message(res, save_dir)
        else:
            return None
    except Exception as e:
        print(f"生成图片异常: {e}")
        return None

# 解析响应消息
def parser_Message(message, save_dir="./"):
    try:
        if not message:
            print("响应消息为空")
            return None
            
        data = json.loads(message)
        
        # 检查是否有header字段
        if 'header' not in data:
            print(f"响应格式异常，缺少header字段: {data}")
            return None
            
        code = data['header']['code']
        if code != 0:
            print(f'请求错误: {code}, {data}')
            return None
        else:
            # 检查payload结构
            if 'payload' not in data or 'choices' not in data['payload'] or 'text' not in data['payload']['choices']:
                print(f"响应格式异常，缺少必要字段: {data}")
                return None
                
            text = data["payload"]["choices"]["text"]
            if not text or len(text) == 0:
                print("响应中没有图片内容")
                return None
                
            imageContent = text[0]
            imageBase = imageContent["content"]
            imageName = data['header']['sid']
            
            # 确保保存路径正确
            if save_dir.endswith('/'):
                save_path = f"{save_dir}{imageName}.jpg"
            else:
                save_path = f"{save_dir}/{imageName}.jpg"
            
            if base64_to_image(imageBase, save_path):
                print("图片保存路径：" + save_path)
                return save_path
            else:
                return None
                
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print(f"原始响应: {message}")
        return None
    except Exception as e:
        print(f"解析消息异常: {e}")
        return None


if __name__ == '__main__':
    # 运行前请配置以下鉴权三要素，获取途径：https://console.xfyun.cn/services/tti
    # 注意：这里的APIKEY和APISECRET在你的代码中是反的
    APPID = 'b18dc113'
    APIKEY = '20082c2448c81bcb4fa76a12c6be12fe'  # 这个是真正的APIKey
    APISECRET = 'NjRkNDk5MWUwNmU1MDg5Y2RjZjczOWM2'  # 这个是真正的APISecret
    desc = '''生成一张图：远处有着高山，山上覆盖着冰雪，近处有着一片湛蓝的湖泊'''
    
    result = generate_picture_by_text(desc, APPID, APIKEY, APISECRET, "./")
    if result:
        print(f"图片生成成功: {result}")
    else:
        print("图片生成失败")