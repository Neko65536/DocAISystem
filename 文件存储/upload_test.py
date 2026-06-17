#!/usr/bin/env python3
"""
七牛云对象存储 - 文件上传测试
"""

import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import QINIU_AK, QINIU_SK, BUCKET_NAME, REGION_ID
from qiniu import Auth, Region, put_file_v2


def upload_file(file_path, save_name=None):
    """
    上传文件到七牛云存储

    Args:
        file_path: 本地文件路径
        save_name: 保存到云端的文件名，默认为原文件名

    Returns:
        (success, result/info)
    """
    if not os.path.exists(file_path):
        return False, f"文件不存在: {file_path}"

    # 生成保存文件名
    if save_name is None:
        save_name = os.path.basename(file_path)

    # 认证
    q = Auth(QINIU_AK, QINIU_SK)

    # 生成上传Token
    token = q.upload_token(BUCKET_NAME, save_name, 3600)

    # 上传文件
    ret, info = put_file_v2(token, save_name, file_path)

    if info.status_code == 200:
        return True, {
            'key': ret.get('key', save_name),
            'hash': ret.get('hash', 'N/A'),
            'url': f"http://{BUCKET_NAME}.s3.cn-east-1.qiniucs.com/{save_name}"
        }
    else:
        return False, info


def upload_text(content, save_name):
    """
    上传文本内容为文件

    Args:
        content: 文本内容
        save_name: 保存的文件名

    Returns:
        (success, result/info)
    """
    # 创建临时文件
    temp_file = f"_temp_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"

    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)

        success, result = upload_file(temp_file, save_name)
        return success, result
    finally:
        # 清理临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)


def main():
    print("=" * 50)
    print("七牛云对象存储 - 文件上传测试")
    print("=" * 50)
    print(f"空间: {BUCKET_NAME}")
    print(f"区域: {REGION_ID}")
    print("=" * 50)

    # 测试1: 上传文本内容
    print("\n[测试1] 上传文本内容...")

    text_content = f"""
七牛云存储测试文件
==================
上传时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
空间名称: {BUCKET_NAME}
存储区域: {REGION_ID}

这是一段测试文本内容。
"""

    success, result = upload_text(text_content, "test_upload.txt")

    if success:
        print(f"  [OK] 上传成功!")
        print(f"       文件名: {result['key']}")
        print(f"       Hash: {result['hash']}")
        print(f"       访问地址: {result['url']}")
    else:
        print(f"  [FAIL] 上传失败: {result}")

    # 测试2: 上传本地文件（如果存在）
    print("\n[测试2] 上传本地文件...")

    # 查找测试目录下的文件
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [f for f in os.listdir(current_dir) if f.endswith(('.txt', '.py', '.md'))]

    if test_files:
        # 上传第一个找到的文件
        test_file = test_files[0]
        print(f"  找到文件: {test_file}")

        success, result = upload_file(test_file, f"backup_{test_file}")

        if success:
            print(f"  [OK] 上传成功!")
            print(f"       文件名: {result['key']}")
            print(f"       Hash: {result['hash']}")
            print(f"       访问地址: {result['url']}")
        else:
            print(f"  [FAIL] 上传失败: {result}")
    else:
        print("  未找到可上传的测试文件")

    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
