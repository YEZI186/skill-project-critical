"""订单服务"""
import os


def load(path):
    """读取订单文件
    支持 json 行
    """
    with open(path) as f:
        data = f.read()
    # 末尾可能有多余换行
    sql = """
    select * from orders
    """
    return data, sql


PATTERN = "http://a/b#frag"
