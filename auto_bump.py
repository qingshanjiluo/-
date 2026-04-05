import os
import json
import time
import random
import string
import re
import signal
import sys
from datetime import datetime, timedelta
from login import BBSTurkeyBotLogin
from post import BBSPoster

class AutoBumpBot:
    def __init__(self):
        self.base_url = os.getenv("BASE_URL", "https://mbbs.zdjl.site/mk48by049.mbbs.cc")
        self.username = os.getenv("BOT_USERNAME")
        self.password = os.getenv("BOT_PASSWORD")
        if not self.username or not self.password:
            raise ValueError("请设置 BOT_USERNAME 和 BOT_PASSWORD")

        self.login_retries = 50

        self.target_category = 5
        self.bump_interval = int(os.getenv("BUMP_INTERVAL", "120"))      # 每个目标帖子的顶帖间隔（秒）
        self.delete_delay = int(os.getenv("DELETE_DELAY", "3"))
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "300"))    # 扫描引导帖间隔
        self.run_duration = int(os.getenv("RUN_DURATION_HOURS", "5"))

        env_guide_id = os.getenv("GUIDE_THREAD_ID")
        if env_guide_id:
            self.guide_thread_id = int(env_guide_id)
            print(f"📌 使用环境变量指定的引导帖 ID: {self.guide_thread_id}")
        else:
            self.state_file = "bump_state.json"
            self.state = self._load_state()
            self.guide_thread_id = self.state.get("guide_thread_id")
            if self.guide_thread_id:
                print(f"📌 从状态文件读取引导帖 ID: {self.guide_thread_id}")

        self.running = True
        self.token = None
        self.user_id = None
        self.session = None
        self.poster = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        print("\n🛑 收到退出信号，正在保存状态并停止...")
        self.running = False

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"guide_thread_id": None}

    def _save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def login(self):
        print("🔐 正在登录论坛...")
        login_bot = BBSTurkeyBotLogin(
            base_url=self.base_url,
            username=self.username,
            password=self.password,
            max_retries=self.login_retries
        )
        success, result, session = login_bot.login_with_retry()
        if not success:
            print("❌ 登录失败")
            return False
        self.token = result['data']['token']
        self.user_id = result['data']['id']
        self.session = session
        self.poster = BBSPoster(session, self.base_url)

        print("⏳ 等待5秒并刷新页面以获取管理员权限...")
        time.sleep(5)
        try:
            self.session.get(self.base_url, timeout=10)
            print("✅ 页面刷新成功")
        except:
            print("⚠️ 页面刷新失败，但继续运行")

        print(f"✅ 登录成功，用户ID: {self.user_id}")
        return True

    def generate_random_text(self, length=20):
        chars = string.ascii_letters + string.digits + "的一是不了人在我有他这中"
        return ''.join(random.choice(chars) for _ in range(length))

    def create_or_get_guide_post(self):
        if self.guide_thread_id:
            print(f"📌 使用已有引导帖 ID: {self.guide_thread_id}")
            detail = self.poster.get_thread_detail(self.token, self.guide_thread_id)
            if detail:
                return self.guide_thread_id
            else:
                print("⚠️ 引导帖已不存在，将重新创建")
                self.guide_thread_id = None
                self.state["guide_thread_id"] = None
                self._save_state()

        for attempt in range(3):
            title = self.generate_random_text(15)
            content = self.generate_random_text(50)
            print(f"📝 发布引导帖 (尝试 {attempt+1}/3): {title}")
            success, thread_data = self.poster.create_thread(self.token, self.target_category, title, content)
            if success and thread_data:
                self.guide_thread_id = thread_data.get('id')
                self.state["guide_thread_id"] = self.guide_thread_id
                self._save_state()
                print(f"✅ 引导帖发布成功，ID: {self.guide_thread_id}")
                return self.guide_thread_id
            else:
                print(f"❌ 引导帖发布失败 (尝试 {attempt+1}/3)")
                if attempt < 2:
                    print("⏳ 等待10秒后重试...")
                    time.sleep(10)

        print("❌ 引导帖创建失败，请检查 API 或手动创建并设置环境变量 GUIDE_THREAD_ID")
        return None

    def get_comments_from_thread(self, thread_id):
        return self.poster.get_post_comments(self.token, thread_id)

    def extract_target_thread_ids(self, comments):
        """从所有评论中提取所有格式为 'ID:xxx' 的帖子ID，返回列表（可能重复）"""
        pattern = re.compile(r'ID[：:]\s*(\d+)', re.IGNORECASE)
        ids = []
        for comment in comments:
            content = comment.get('content', '')
            matches = pattern.findall(content)
            for match in matches:
                ids.append(int(match))
        return ids

    def bump_thread(self, thread_id):
        """对单个帖子执行一轮顶帖（发评论后删除）"""
        print(f"🚀 顶帖: 帖子ID {thread_id}")
        comment = f"顶一下 {random.randint(1, 100)}"
        success, comment_id = self.poster.create_comment(self.token, thread_id, comment)
        if not success or not comment_id:
            print(f"❌ 发布评论失败，跳过 {thread_id}")
            return False
        time.sleep(self.delete_delay)
        self.poster.delete_comment(self.token, comment_id)
        print(f"✅ 顶帖完成: {thread_id}")
        return True

    def run(self):
        if not self.login():
            return

        guide_id = self.create_or_get_guide_post()
        if not guide_id:
            print("❌ 无法获取引导帖，退出")
            return

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=self.run_duration)
        print(f"⏰ 机器人将运行至 {end_time.strftime('%Y-%m-%d %H:%M:%S')} (共 {self.run_duration} 小时)")
        print(f"⏱️ 每 {self.check_interval} 秒检查一次引导帖\n")

        while self.running and datetime.now() < end_time:
            print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] 检查引导帖...")
            comments = self.get_comments_from_thread(guide_id)
            print(f"📋 获取到 {len(comments)} 条评论")

            target_ids = self.extract_target_thread_ids(comments)
            if not target_ids:
                print("ℹ️ 未找到格式为 'ID:xxx' 的评论")
            else:
                # 去重（可选，不去重也可以，但重复执行同一帖子可能浪费资源）
                unique_ids = list(set(target_ids))
                print(f"🎯 发现目标帖子ID: {unique_ids}")
                for tid in unique_ids:
                    self.bump_thread(tid)
                    # 每个目标帖子顶帖后等待间隔，避免过于频繁
                    time.sleep(self.bump_interval)

            remaining = (end_time - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            wait = min(self.check_interval, remaining)
            print(f"⏳ 等待 {wait} 秒后下次检查...")
            for _ in range(int(wait)):
                if not self.running or datetime.now() >= end_time:
                    break
                time.sleep(1)

        print(f"\n✅ 运行结束，总耗时 {self.run_duration} 小时")
        self._save_state()

if __name__ == "__main__":
    bot = AutoBumpBot()
    bot.run()
