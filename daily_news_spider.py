#!/usr/bin/env python
# -*- coding: utf-8 -*-

# @File    : daily_news_spider.py
# @Contact : youker_shawn@163.com
import time

import requests
from urllib.parse import urlencode
import datetime
import jinja2
import zmail
import re
from lxml import etree
import pymongo

__author__ = 'youker'
__date__ = '2018/8/21 0021 14:54'

'''
今XX条，“西安教育”新闻类爬虫
'''


def get_data_list(offset):
    """
    获取原始新闻信息列表，json格式
    ajax请求地址  https://www.toutiao.com/search_content/?offset=0&format=json&keyword=%E8%A5%BF%E5%AE%89%E6%95%99%E8%82%B2&autoload=true&count=20&cur_tab=1&from=search_tab
    :return: 提取返回的json格式中的data，便于直接提取，以及判断是否停止请求
    """
    params = {
        'offset': offset,  # 经分析，每次ajax请求只变动此处，递增20
        'format': 'json',
        'keyword': '西安教育',
        'autoload': 'true',
        'count': '20',
        'cur_tab': '1',
        'from': 'search_tab',
    }
    url = 'https://www.toutiao.com/search_content/?' + urlencode(params)
    head = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36'}
    try:
        response = requests.get(url, headers=head)
        if response.status_code == 200:
            data_dict = response.json()   # 分析得知返回json数据，直接调用方法解析为字典对象
            if not data_dict.get('data'):  # 超出ajax可获取的更多内容offset之后，就停止
                return None
            return data_dict['data']
    except requests.ConnectionError:
        return None


def parse_data_list(data_list):
    """
    解析json数据，
    根据发布时间，只对当日的新闻进行提取（第二天早上发送）
    提取：标题、发布时间、发布方、摘要、源url（需要组装好），保存为字典对象
    :param data_list:新闻json列表，需要进行提取
    :return: 字典对象的list，提供进行下一步跳转
    """
    today = str(datetime.datetime.now()).split()[0]
    news_list = []
    for item in data_list:
        # 保证是新闻项，且获取当日新闻，否则跳过
        if item.get('source_url') and item.get('datetime') and item['datetime'].split()[0] == today:
            news = {
                'title': item['title'],
                'datetime': item['datetime'],
                'source': item['source'],
                'abstract': item['abstract'],
                'source_url': 'https://www.toutiao.com' + item['source_url'],
            }
            news_list.append(news)
    return news_list


def get_news_detail(news_url):
    """
    请求得到详情页
    :return: 详情页
    """
    try:
        head = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36',
        }
        # 未添加该字段，可能被识别为爬虫，导致无法获取HTML
        response = requests.get(news_url, headers=head)
        if response.status_code == 200:
            return response.text
    except requests.ConnectionError:
        return None


def parse_news_detail(detail_html):
    """
    提取藏在JS中的目标新闻的HTML文档（html敏感字符是字符实体形式,需转换）
    :return:经转换并剔除图片标签后得到的纯文本内容
    """
    # 根据规律，编写正则表达式
    pattern = re.compile('articleInfo:.*?content: \'(.*?&gt;)\',.*?groupId:', re.S)
    result = re.search(pattern, detail_html)
    if result:
        article_js = result.group(1)
        # 转换实体名称为标签，便于剔除img相关标签以及提取内容
        article_js = article_js.replace('&lt;', '<').replace('&gt;', '>')
        article_html = re.sub('<div class.*?/div>', '', article_js)
        # 使用Xpath解析，提取出文本
        html = etree.HTML(article_html)
        result = html.xpath('//text()')   # 文本段落列表
        return '\n'.join(result)
    else:
        return None


def create_email_htmlcontent(news_list):
    """
    根据新闻列表，迭代每则新闻，生成HTML邮件内容
    :param news_list: 新闻列表
    :return: HTML内容
    """
    # 使用jinja2模板渲染
    # 1.配置模板文件搜索路径
    TemplateLoader = jinja2.FileSystemLoader(searchpath='F:/code_lxy/Python3/news_spider/')
    # 2.创建环境变量
    TemplateEnv = jinja2.Environment(loader=TemplateLoader)

    # 3.加载模板，渲染数据
    template_name = 'email_content.html'
    template = TemplateEnv.get_template(template_name)
    html = template.render({'news_list': news_list})
    return html


def send_email(news_list):
    """
    发送每日新闻邮件
    从解析列表页返回的字典列表数据中提取：标题，时间，发布方，新闻详情页链接，写成html发送邮件
    :param news_list: 新闻字典对象的列表
    :return: 发送成功与否
    """
    # 使用邮箱作为发送方
    server = zmail.server('发送方的邮箱', '邮箱登录密码')

    # SMTP function.
    if server.smtp_able():
        print('SMTP 功能已开启')
    else:
        print('SMTP 未开启')
        return False
    # POP function.
    if server.pop_able():
        print('POP 功能已开启')
    else:
        print('POP 功能未开启')
        return False

    html_content = create_email_htmlcontent(news_list)
    mail = {
        'subject': '***youker每日新闻推送服务***',
        'content-html': html_content,
    }
    # 对目标邮箱进行发送，返回发送结果,文件较大可能会进入垃圾邮件
    return server.send_mail('接收方的邮箱', mail)


def save_to_mongodb(news):
    """
    将包含详情内容的字典对象，处理后，存入Mongodb数据库
    :return:
    """
    client = pymongo.MongoClient(MONGO_URL)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    try:
        if collection.insert_one(news):
            print('存储到Mongodb成功！')
    except Exception:
        print('存储到Mongodb失败！')


def start_spider():
    offset = 0
    news_list = []
    # 初次获取列表页
    data_list = get_data_list(offset)
    while data_list:
        print('请求到第%d组数据~' % int(offset / 20))
        # 对原生的新闻列表进行提取，返回所需的新闻字典对象的列表（未请求详情内容）
        # 并添加进新闻列表
        news_list.extend(parse_data_list(data_list))

        # 请求下一组原生新闻列表页
        time.sleep(3)
        offset += 20
        # 返回为None时，说明json中data为空，即刷新到尾部，可以停止
        data_list = get_data_list(offset)

    # for news in news_list:
    #     print(news)

    # 对所有的当天新闻，进行发送邮件，以及保存数据库操作
    if send_email(news_list):
        print('邮件已发出')

    for news in news_list:
        # 获取详情页html
        detail_html = get_news_detail(news['source_url'])
        # 提取js中的文章数据，转换为HTML，剔除img标签，提取文本
        article = parse_news_detail(detail_html)
        # 文章文本内容保存进字典
        news['article'] = article
        # 对单则新闻进行保存操作
        save_to_mongodb(news)


if __name__ == '__main__':
    MONGO_URL = 'localhost'
    MONGO_DB = 'news_spider_db'
    MONGO_COLLECTION = 'news'

    start_spider()

