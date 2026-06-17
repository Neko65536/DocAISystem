#!/usr/bin/env python3
"""
七牛云对象存储测试脚本
空间: docs1122
区域: 华东-浙江 (cn-east-1)
"""

import os
import uuid
from datetime import datetime
from qiniu import Auth, BucketManager, Region, put_file_v2

# 七牛云凭据
AK = "_mbXMWftatd8Kfvtulobc4dtlYZv2CARUtCEdbSy"
SK = "O1ZyzFy00cQ8gjID7JrJ2CtrpQemCxLEtLznALMj"

# 空间配置
BUCKET_NAME = "docs1122"

# 创建华东-浙江区域
region = Region.from_region_id('cn-east-1')


def test_bucket_list():
    """测试列举空间中的文件"""
    print("\n" + "="*50)
    print("1. 测试列举文件")
    print("="*50)

    q = Auth(AK, SK)
    bucket = BucketManager(q)

    # 列举文件
    ret, eof, info = bucket.list(BUCKET_NAME)

    if info.status_code == 200:
        print(f"[OK] 空间 {BUCKET_NAME} 连接成功!")
        print(f"     API 响应状态: {info.status_code}")

        if ret and ret.get('items'):
            print(f"\n文件列表 (共 {len(ret['items'])} 个文件):")
            print("-" * 60)
            for item in ret['items']:
                size_kb = int(item.get('fsize', 0)) / 1024
                print(f"  {item['key']:<30} {size_kb:.2f} KB")
        else:
            print("\n空间为空，没有文件")

        if ret and ret.get('commonPrefixes'):
            print(f"\n目录前缀:")
            for prefix in ret['commonPrefixes']:
                print(f"  {prefix}")
    else:
        print(f"[FAIL] 列举失败: {info.error}")
        print(f"       状态码: {info.status_code}")


def test_bucket_stat():
    """获取空间状态信息"""
    print("\n" + "="*50)
    print("2. 测试获取空间状态")
    print("="*50)

    q = Auth(AK, SK)
    bucket = BucketManager(q)

    # 尝试获取一个文件来验证空间存在
    ret, eof, info = bucket.list(BUCKET_NAME, limit=1)

    if info.status_code == 200:
        print(f"[OK] 空间 {BUCKET_NAME} 存在且可访问")
        print(f"     区域: 华东-浙江 (cn-east-1)")
    else:
        print(f"[FAIL] 获取空间状态失败: {info.error}")


def test_domain_access():
    """测试访问空间域名"""
    print("\n" + "="*50)
    print("3. 测试空间域名访问")
    print("="*50)

    domains = [
        f"http://{BUCKET_NAME}.s3.cn-east-1.qiniucs.com",
        f"https://{BUCKET_NAME}.s3.cn-east-1.qiniucs.com"
    ]

    print("域名列表:")
    for domain in domains:
        print(f"  {domain}")


def test_upload():
    """测试上传文件"""
    print("\n" + "="*50)
    print("4. 测试上传文件")
    print("="*50)

    q = Auth(AK, SK)

    # 创建测试文件
    test_content = f"七牛云存储测试文件\n时间: {datetime.now().isoformat()}\n空间: {BUCKET_NAME}\n"
    test_filename = f"test_{uuid.uuid4().hex[:8]}.txt"

    with open(test_filename, 'w', encoding='utf-8') as f:
        f.write(test_content)

    print(f"创建测试文件: {test_filename}")

    # 生成上传Token
    token = q.upload_token(BUCKET_NAME, test_filename, 3600)

    ret, info = put_file_v2(token, test_filename, test_filename)

    if info.status_code == 200:
        print(f"[OK] 上传成功!")
        print(f"     文件名: {ret.get('key')}")
        print(f"     Hash: {ret.get('hash')}")
        print(f"     文件大小: {ret.get('fsize', 'N/A')} bytes")
        print(f"\n访问链接:")
        print(f"  http://{BUCKET_NAME}.s3.cn-east-1.qiniucs.com/{test_filename}")
        return test_filename
    else:
        print(f"[FAIL] 上传失败: {info.error}")
        return None


def test_delete(filename):
    """删除测试上传的文件"""
    if not filename:
        return

    print("\n" + "="*50)
    print("5. 删除测试文件")
    print("="*50)

    q = Auth(AK, SK)
    bucket = BucketManager(q)

    ret, info = bucket.delete(BUCKET_NAME, filename)
    if info.status_code == 200:
        print(f"[OK] 已删除: {filename}")
    else:
        print(f"[FAIL] 删除失败 {filename}: {info.error}")


def test_delete_all_test_files():
    """删除所有测试上传的文件"""
    print("\n" + "="*50)
    print("6. 清理所有测试文件")
    print("="*50)

    q = Auth(AK, SK)
    bucket = BucketManager(q)

    # 获取测试文件
    ret, eof, info = bucket.list(BUCKET_NAME, prefix="test_")

    if ret and ret.get('items'):
        for item in ret['items']:
            key = item['key']
            ret, info = bucket.delete(BUCKET_NAME, key)
            if info.status_code == 200:
                print(f"[OK] 已删除: {key}")
            else:
                print(f"[FAIL] 删除失败 {key}: {info.error}")
    else:
        print("没有找到测试文件需要删除")


def main():
    print("="*50)
    print("七牛云对象存储测试工具")
    print(f"   空间: {BUCKET_NAME}")
    print(f"   区域: 华东-浙江")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    uploaded_file = None

    try:
        # 测试基本连接
        test_domain_access()
        test_bucket_stat()
        test_bucket_list()

        # 测试上传
        uploaded_file = test_upload()

        # 测试删除
        if uploaded_file:
            test_delete(uploaded_file)
        test_delete_all_test_files()

        print("\n" + "="*50)
        print("测试完成!")
        print("="*50)

        print("\n空间访问信息:")
        print(f"  S3协议外网访问: https://docs1122.s3.cn-east-1.qiniucs.com")
        print(f"  控制台地址: https://portal.qiniu.com/")

    except Exception as e:
        print(f"\n[ERROR] 测试过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理本地测试文件
        for f in os.listdir('.'):
            if f.startswith('test_') and f.endswith('.txt'):
                try:
                    os.remove(f)
                    print(f"清理本地文件: {f}")
                except:
                    pass


if __name__ == "__main__":
    main()
