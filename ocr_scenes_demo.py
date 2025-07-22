import requests
import time
import hashlib
import base64

URL = "http://tupapi.xfyun.cn/v1/scene"
APPID = "b18dc113"
API_KEY = "20082c2448c81bcb4fa76a12c6be12fe"

def getHeader(image_name, image_url=None):
    curTime = str(int(time.time()))
    param = "{\"image_name\":\"" + image_name + "\",\"image_url\":\"" + image_url + "\"}"
    paramBase64 = base64.b64encode(param.encode('utf-8'))
    tmp = str(paramBase64, 'utf-8')

    m2 = hashlib.md5()
    m2.update((API_KEY + curTime + tmp).encode('utf-8'))
    checkSum = m2.hexdigest()

    header = {
        'X-CurTime': curTime,
        'X-Param': paramBase64,
        'X-Appid': APPID,
        'X-CheckSum': checkSum,
    }
    return header

def ocr_image_url(image_name, image_url):
    headers = getHeader(image_name, image_url)
    r = requests.post(URL, headers=headers)
    return r.content

# 新增：支持本地图片上传
def ocr_image_file(file_bytes, image_name="uploaded.jpg"):
    # 你可以用第三方图床上传图片，获得url后用ocr_image_url
    # 或者直接用讯飞支持的本地图片接口（如有）
    # 这里只做演示，假设只能用url
    return "暂未实现本地图片直传，请先上传到图床获得url"
