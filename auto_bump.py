import os
import json
import time
import random
import string
import re
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

        # 状态文件
        self.state_file = "bump_state.json"
        self.state = self._load_state()

        self.token = None
        self.user_id = None
        self.session = None
        self.poster = None

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"processed_threads": []}   # 已处理过的目标帖子ID

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
        """生成随机乱码（中文+数字+字母）"""
        chars = string.ascii_letters + string.digits + "的一是不了人在我有他这中"
        return ''.join(random.choice(chars) for _ in range(length))

    def create_bump_post(self):
        """在板块5发布一个乱码帖子，返回帖子ID"""
        title = self.generate_random_text(15)
        content = self.generate_random_text(50)
        print(f"📝 发布引导帖: {title}")
        success, thread_data = self.poster.create_thread(self.token, self.target_category, title, content)
        if success and thread_data:
            thread_id = thread_data.get('id')
            print(f"✅ 引导帖发布成功，ID: {thread_id}")
            return thread_id
        else:
            print("❌ 引导帖发布失败")
            return None

    def get_comments_from_thread(self, thread_id):
        """获取帖子下的所有评论，返回评论列表"""
        comments = self.poster.get_post_comments(self.token, thread_id)
        return comments

    def extract_target_thread_id(self, comments):
        """从评论中提取格式为 'ID:xxx' 的目标帖子ID"""
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
        """对指定帖子进行多轮顶帖（评论后删除）"""
        print(f"\n🚀 开始顶帖，目标帖子ID: {thread_id}，共 {rounds} 轮")
        for i in range(rounds):
            print(f"\n--- 第 {i+1}/{rounds} 轮 ---")
            # 发评论
            comment = f"顶一下 {random.randint(1, 100)}"
            success, comment_id = self.poster.create_comment(self.token, thread_id, comment)
            if not success or not comment_id:
                print("❌ 发布评论失败，停止顶帖")
                break
            # 等待后删除
            time.sleep(self.delete_delay)
            self.poster.delete_comment(self.token, comment_id)
            print(f"✅ 第 {i+1} 轮顶帖完成")
            # 如果不是最后一轮，等待间隔
            if i < rounds - 1:
                print(f"⏳ 等待 {self.bump_interval} 秒后继续...")
                time.sleep(self.bump_interval)
        print(f"🎉 顶帖完成: {thread_id}")

    def run_once(self):
        """单次运行：发帖 → 获取评论 → 提取目标ID → 顶帖 → 记录"""
        if not self.login():
            return

        # 1. 发布引导帖
        guide_thread_id = self.create_bump_post()
        if not guide_thread_id:
            print("❌ 无法创建引导帖，退出")
            return

        # 2. 等待一段时间让用户评论
        wait_time = 60  # 等待60秒，给用户时间评论
        print(f"⏳ 等待 {wait_time} 秒，等待用户评论 'ID:xxx'...")
        time.sleep(wait_time)

        # 3. 获取评论
        comments = self.get_comments_from_thread(guide_thread_id)
        print(f"📋 获取到 {len(comments)} 条评论")

        # 4. 提取目标帖子ID
        target_id = self.extract_target_thread_id(comments)
        if not target_id:
            print("❌ 未找到格式为 'ID:xxx' 的评论，本次运行结束")
            # 可选：删除引导帖
            self.poster.delete_thread(self.token, guide_thread_id)
            return

        # 5. 检查是否已处理过
        if target_id in self.state["processed_threads"]:
            print(f"⏭️ 帖子 {target_id} 已处理过，跳过")
            return

        # 6. 执行顶帖
        self.bump_thread(target_id, self.bump_rounds)

        # 7. 记录已处理
        self.state["processed_threads"].append(target_id)
        self._save_state()

        # 8. 可选：删除引导帖
        self.poster.delete_thread(self.token, guide_thread_id)
        print("🗑️ 已删除引导帖")

if __name__ == "__main__":
    bot = AutoBumpBot()
    bot.run_once()
