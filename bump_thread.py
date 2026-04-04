import os
import time
import random
import signal
import sys
from login import BBSTurkeyBotLogin
from post import BBSPoster

class BumpBot:
    def __init__(self, thread_id, comment_text, interval=120, delete_delay=3):
        """
        :param thread_id: 要顶的帖子ID
        :param comment_text: 评论内容（可以是列表，随机选择）
        :param interval: 两次顶帖之间的间隔（秒），默认120秒
        :param delete_delay: 发布评论后等待多少秒再删除，默认3秒
        """
        self.base_url = os.getenv("BASE_URL", "https://mbbs.zdjl.site/mk48by049.mbbs.cc")
        self.username = os.getenv("BOT_USERNAME")
        self.password = os.getenv("BOT_PASSWORD")
        if not self.username or not self.password:
            raise ValueError("请设置环境变量 BOT_USERNAME 和 BOT_PASSWORD")

        self.thread_id = thread_id
        self.comment_text = comment_text
        self.interval = interval
        self.delete_delay = delete_delay
        self.token = None
        self.user_id = None
        self.session = None
        self.poster = None
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        print("\n🛑 收到退出信号，正在停止...")
        self.running = False

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

    def get_random_comment(self):
        if isinstance(self.comment_text, list):
            return random.choice(self.comment_text)
        return self.comment_text

    def bump_once(self):
        """执行一轮顶帖：发评论 → 等待 → 删除评论"""
        comment = self.get_random_comment()
        print(f"\n📤 发布评论: {comment[:50]}...")
        success, comment_id = self.poster.create_comment(self.token, self.thread_id, comment)
        if not success or not comment_id:
            print("❌ 发布评论失败，本轮结束")
            return False

        print(f"⏳ 等待 {self.delete_delay} 秒后删除评论...")
        time.sleep(self.delete_delay)

        print(f"🗑️ 删除评论 ID: {comment_id}")
        del_success = self.poster.delete_comment(self.token, comment_id)
        if del_success:
            print("✅ 顶帖成功（评论已删除）")
        else:
            print("⚠️ 删除评论失败，但顶帖效果可能仍在")
        return True

    def run(self):
        if not self.login():
            return

        print(f"🚀 开始顶帖，目标帖子ID: {self.thread_id}")
        print(f"⏱️ 间隔: {self.interval} 秒，删除延迟: {self.delete_delay} 秒")
        print("按 Ctrl+C 停止\n")

        cycle = 0
        while self.running:
            cycle += 1
            print(f"\n========== 第 {cycle} 轮 ==========")
            self.bump_once()
            if self.running:
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)
        print("👋 机器人已停止")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="论坛顶帖机器人（评论后删除）")
    parser.add_argument("thread_id", type=int, help="要顶的帖子ID")
    parser.add_argument("--comment", "-c", default="顶一下", help="评论内容（可多次使用，随机选择）", action="append")
    parser.add_argument("--interval", "-i", type=int, default=120, help="顶帖间隔（秒），默认120")
    parser.add_argument("--delete-delay", "-d", type=int, default=3, help="发布后等待多少秒删除，默认3")
    args = parser.parse_args()

    if not args.comment:
        comments = ["顶一下"]
    else:
        comments = args.comment

    bot = BumpBot(
        thread_id=args.thread_id,
        comment_text=comments,
        interval=args.interval,
        delete_delay=args.delete_delay
    )
    bot.run()
