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

        # 配置
        self.target_category = 5                     # 板块5
        self.bump_interval = int(os.getenv("BUMP_INTERVAL", "120"))      # 顶帖间隔（秒）
        self.delete_delay = int(os.getenv("DELETE_DELAY", "3"))          # 删除延迟
        self.bump_rounds = int(os.getenv("BUMP_ROUNDS", "10"))           # 每个目标帖子顶帖次数
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "300"))    # 检查引导帖间隔（秒），默认5分钟
        self.run_duration = int(os.getenv("RUN_DURATION_HOURS", "5"))    # 运行时长（小时），默认5小时

        # 状态文件
        self.state_file = "bump_state.json"
        self.state = self._load_state()

        # 引导帖ID（从状态文件读取或为None）
        self.guide_thread_id = self.state.get("guide_thread_id")
        self.running = True

        self.token = None
        self.user_id = None
        self.session = None
        self.poster = None

        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        print("\n🛑 收到退出信号，正在保存状态并停止...")
        self.running = False

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"processed_threads": [], "guide_thread_id": None}

    def _save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def login(self):
        print("🔐 正在登录论坛...")
        login_bot = BBSTurkeyBotLogin(self.base_url, self.username, self.password, max_retries=3)
        success, result, session = login_bot.login_with_retry()
        if not success:
            print("❌ 登录失败")
            return False
        self.token = result['data']['token']
        self.user_id = result['data']['id']
        self.session = session
        self.poster = BBSPoster(session, self.base_url)
        print(f"✅ 登录成功，用户ID: {self.user_id}")
        return True

    def generate_random_text(self, length=20):
        chars = string.ascii_letters + string.digits + "的一是不了人在我有他这中"
        return ''.join(random.choice(chars) for _ in range(length))

    def create_or_get_guide_post(self):
        """创建或获取已有的引导帖ID"""
        if self.guide_thread_id:
            print(f"📌 使用已有引导帖 ID: {self.guide_thread_id}")
            # 检查帖子是否存在
            detail = self.poster.get_thread_detail(self.token, self.guide_thread_id)
            if detail:
                return self.guide_thread_id
            else:
                print("⚠️ 引导帖已不存在，将重新创建")
                self.guide_thread_id = None
                self.state["guide_thread_id"] = None
                self._save_state()

        # 创建新引导帖
        title = self.generate_random_text(15)
        content = self.generate_random_text(50)
        print(f"📝 发布引导帖: {title}")
        success, thread_data = self.poster.create_thread(self.token, self.target_category, title, content)
        if success and thread_data:
            self.guide_thread_id = thread_data.get('id')
            self.state["guide_thread_id"] = self.guide_thread_id
            self._save_state()
            print(f"✅ 引导帖发布成功，ID: {self.guide_thread_id}")
            return self.guide_thread_id
        else:
            print("❌ 引导帖发布失败")
            return None

    def get_comments_from_thread(self, thread_id):
        comments = self.poster.get_post_comments(self.token, thread_id)
        return comments

    def extract_target_thread_id(self, comments):
        pattern = re.compile(r'ID[：:]\s*(\d+)', re.IGNORECASE)
        for comment in comments:
            content = comment.get('content', '')
            match = pattern.search(content)
            if match:
                target_id = int(match.group(1))
                print(f"🎯 从评论中提取到目标帖子ID: {target_id}")
                return target_id
        return None

    def bump_thread(self, thread_id, rounds):
        print(f"\n🚀 开始顶帖，目标帖子ID: {thread_id}，共 {rounds} 轮")
        for i in range(rounds):
            if not self.running:
                break
            print(f"\n--- 第 {i+1}/{rounds} 轮 ---")
            comment = f"顶一下 {random.randint(1, 100)}"
            success, comment_id = self.poster.create_comment(self.token, thread_id, comment)
            if not success or not comment_id:
                print("❌ 发布评论失败，停止顶帖")
                break
            time.sleep(self.delete_delay)
            self.poster.delete_comment(self.token, comment_id)
            print(f"✅ 第 {i+1} 轮顶帖完成")
            if i < rounds - 1 and self.running:
                print(f"⏳ 等待 {self.bump_interval} 秒后继续...")
                time.sleep(self.bump_interval)
        print(f"🎉 顶帖完成: {thread_id}")

    def run(self):
        """持续运行5小时，每5分钟检查一次引导帖"""
        if not self.login():
            return

        # 创建或获取引导帖
        guide_id = self.create_or_get_guide_post()
        if not guide_id:
            print("❌ 无法创建引导帖，退出")
            return

        start_time = datetime.now()
        end_time = start_time + timedelta(hours=self.run_duration)
        print(f"⏰ 机器人将运行至 {end_time.strftime('%Y-%m-%d %H:%M:%S')} (共 {self.run_duration} 小时)")
        print(f"⏱️ 每 {self.check_interval} 秒检查一次引导帖\n")

        while self.running and datetime.now() < end_time:
            print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] 检查引导帖...")
            comments = self.get_comments_from_thread(guide_id)
            print(f"📋 获取到 {len(comments)} 条评论")

            target_id = self.extract_target_thread_id(comments)
            if target_id:
                if target_id in self.state["processed_threads"]:
                    print(f"⏭️ 帖子 {target_id} 已处理过，跳过")
                else:
                    self.bump_thread(target_id, self.bump_rounds)
                    self.state["processed_threads"].append(target_id)
                    self._save_state()
                    print(f"✅ 已记录目标帖子 {target_id}，本次运行不再重复处理")
            else:
                print("ℹ️ 未找到格式为 'ID:xxx' 的评论")

            # 等待下一轮检查
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
