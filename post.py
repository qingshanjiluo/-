import requests
import json
import re

class BBSPoster:
    def __init__(self, session, base_url):
        """
        :param session: requests.Session 对象，已登录
        :param base_url: 论坛根地址，如 https://mk48by049.mbbs.cc
        """
        self.session = session
        self.base_url = base_url.rstrip('/')

    def _get_formhash(self, url):
        """从页面提取 formhash"""
        resp = self.session.get(url)
        match = re.search(r'<input type="hidden" name="formhash" value="([^"]+)"', resp.text)
        if match:
            return match.group(1)
        return None

    def get_threads(self, token, category_id, limit=30):
        """
        获取板块下的帖子列表
        :param token: 登录 token（实际上可能不需要，这里保留接口兼容）
        :param category_id: 板块 ID
        :param limit: 获取数量
        :return: 帖子列表，每个帖子包含 id, title, content 等
        """
        try:
            # 实际论坛 API 可能不同，这里用模拟方式：访问板块页面并解析
            url = f"{self.base_url}/forum.php?mod=forumdisplay&fid={category_id}&orderby=dateline"
            resp = self.session.get(url)
            # 简单解析帖子列表（实际可能需要更健壮的 HTML 解析，这里用正则提取关键信息）
            # 注意：此方法依赖论坛 HTML 结构，可能需要调整
            import re
            threads = []
            # 匹配帖子链接
            pattern = r'<a href="thread-(\d+)-1-1\.html" onclick="atarget\(this\)" class="s xst">(.*?)</a>'
            matches = re.findall(pattern, resp.text)
            for tid, title in matches[:limit]:
                # 获取帖子内容
                thread_content = self.get_post_content(tid)
                threads.append({
                    "id": int(tid),
                    "title": title.strip(),
                    "content": thread_content,
                })
            return threads
        except Exception as e:
            print(f"获取帖子列表失败: {e}")
            return []

    def get_post_content(self, thread_id):
        """获取单个帖子的内容"""
        try:
            url = f"{self.base_url}/thread-{thread_id}-1-1.html"
            resp = self.session.get(url)
            # 简单提取帖子内容（第一个帖子内容）
            import re
            # 匹配 <div class="t_f"> 内的内容
            match = re.search(r'<div class="t_f">(.*?)</div>', resp.text, re.S)
            if match:
                content = re.sub(r'<[^>]+>', '', match.group(1))  # 去除 HTML 标签
                return content.strip()
            return ""
        except Exception as e:
            print(f"获取帖子内容失败: {e}")
            return ""

    def create_comment(self, token, thread_id, content):
        """
        回复帖子（发布评论）
        :param token: 登录 token（实际上可能不需要）
        :param thread_id: 帖子 ID
        :param content: 评论内容
        :return: 是否成功
        """
        try:
            # 获取发帖页面，得到 formhash
            url = f"{self.base_url}/forum.php?mod=post&action=reply&fid=2&tid={thread_id}&extra=&replysubmit=yes"
            formhash = self._get_formhash(url)
            if not formhash:
                print("无法获取 formhash")
                return False

            data = {
                'formhash': formhash,
                'message': content,
                'subject': '',
                'usesig': 1,
                'noticeauthor': 1,
                'wysiwyg': 1,
            }
            post_url = f"{self.base_url}/forum.php?mod=post&action=reply&fid=2&tid={thread_id}&extra=&replysubmit=yes"
            resp = self.session.post(post_url, data=data)
            if resp.status_code == 200 and '发表回复成功' in resp.text:
                return True
            else:
                print(f"发表回复失败: {resp.status_code}")
                return False
        except Exception as e:
            print(f"发表评论异常: {e}")
            return False

    def create_post(self, token, category_id, title, content):
        """
        发布新帖子
        :param token: 登录 token
        :param category_id: 板块 ID
        :param title: 标题
        :param content: 内容
        :return: 是否成功
        """
        try:
            # 获取发帖页面
            url = f"{self.base_url}/forum.php?mod=post&action=newthread&fid={category_id}"
            formhash = self._get_formhash(url)
            if not formhash:
                print("无法获取 formhash")
                return False

            data = {
                'formhash': formhash,
                'subject': title,
                'message': content,
                'usesig': 1,
                'noticeauthor': 1,
                'wysiwyg': 1,
            }
            post_url = f"{self.base_url}/forum.php?mod=post&action=newthread&fid={category_id}&extra=&topicsubmit=yes"
            resp = self.session.post(post_url, data=data)
            if resp.status_code == 200 and '发表成功' in resp.text:
                return True
            else:
                print(f"发帖失败: {resp.status_code}")
                return False
        except Exception as e:
            print(f"发帖异常: {e}")
            return False
