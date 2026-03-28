import os
import json
import time
import argparse
import asyncio
import requests
import base64
from datetime import datetime
from login import ForumLogin
from post import BBSPoster
from deepseek_client import DeepSeekClient
from deepseek_payment import DeepSeekPayment

class PaymentBot:
    def __init__(self):
        self.base_url = os.getenv("BASE_URL", "https://mk48by049.mbbs.cc")
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")
        self.client = DeepSeekClient(api_key=self.api_key)

        # DeepSeek 账号（用于自动充值）
        self.ds_username = os.getenv("DEEPSEEK_USERNAME")
        self.ds_password = os.getenv("DEEPSEEK_PASSWORD")
        if not self.ds_username or not self.ds_password:
            raise ValueError("请设置 DEEPSEEK_USERNAME 和 DEEPSEEK_PASSWORD")

        # 图床配置（imgbb）
        self.imgbb_api_key = os.getenv("IMGBB_API_KEY")
        if not self.imgbb_api_key:
            print("⚠️ 未设置 IMGBB_API_KEY，将无法上传截图")

        # 论坛会话
        self.session = None
        self.token = None
        self.user_id = None

        # 已处理请求记录
        self.processed_file = "processed_requests.json"
        self.processed = self._load_processed()

        # 监听的目标板块
        self.target_categories = [
            int(x) for x in os.getenv("LISTEN_CATEGORIES", "2,5").split(",") if x
        ]
        self.max_threads = int(os.getenv("MAX_THREADS", "30"))

    def _load_processed(self):
        if os.path.exists(self.processed_file):
            with open(self.processed_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_processed(self):
        with open(self.processed_file, 'w', encoding='utf-8') as f:
            json.dump(self.processed, f, indent=2)

    def login_forum(self):
        """登录论坛"""
        username = os.getenv("BOT_USERNAME")
        password = os.getenv("BOT_PASSWORD")
        if not username or not password:
            raise ValueError("请设置环境变量 BOT_USERNAME 和 BOT_PASSWORD")
        login_obj = ForumLogin()
        success, self.session, self.token, self.user_id = login_obj.login(
            username, password, retries=3
        )
        if not success:
            print("❌ 论坛登录失败")
            return False
        print("✅ 论坛登录成功")
        return True

    def parse_payment_info(self, content):
        """
        使用 AI 解析帖子内容中的金额和支付方式
        返回 dict { "amount": int, "method": "wechat"|"alipay"|None }
        """
        prompt = f"""
请从以下文本中提取充值金额和支付方式。金额必须是正整数（单位元），支付方式可能是“微信”、“支付宝”、“微信支付”、“支付宝支付”等。
输出格式为JSON：{{"amount": 数字, "method": "wechat" 或 "alipay"}}。
如果无法提取，返回 {{"error": "原因"}}。
文本：{content}
        """
        response = self.client.generate(prompt, max_tokens=100, temperature=0.3)
        try:
            result = json.loads(response.strip())
            if "error" in result:
                return None
            amount = int(result.get("amount"))
            method = result.get("method")
            if amount > 0 and method in ["wechat", "alipay"]:
                return {"amount": amount, "method": method}
        except:
            # 降级：简单正则
            import re
            match = re.search(r"(\d+)\s*元", content)
            amount = int(match.group(1)) if match else None
            method = None
            if "微信" in content or "wechat" in content.lower():
                method = "wechat"
            elif "支付宝" in content or "alipay" in content.lower():
                method = "alipay"
            if amount and method:
                return {"amount": amount, "method": method}
        return None

    def upload_to_imgbb(self, image_bytes):
        """上传图片到 imgbb 图床，返回图片 URL"""
        if not self.imgbb_api_key:
            return None
        url = "https://api.imgbb.com/1/upload"
        data = {
            "key": self.imgbb_api_key,
            "image": base64.b64encode(image_bytes).decode('utf-8')
        }
        try:
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return result["data"]["url"]
        except Exception as e:
            print(f"上传图床失败: {e}")
        return None

    def reply_with_payment_code(self, thread_id, payment_info, qrcode_bytes):
        """回复帖子，包含付款码图片"""
        amount = payment_info["amount"]
        method_name = "微信支付" if payment_info["method"] == "wechat" else "支付宝"

        # 上传截图
        img_url = self.upload_to_imgbb(qrcode_bytes) if self.imgbb_api_key else None

        if img_url:
            reply = f"""💰 已收到您的充值请求！

**金额**：{amount} 元
**支付方式**：{method_name}

请使用 {method_name} 扫描下方二维码完成支付：

![付款码]({img_url})

*注意：请尽快扫码支付，二维码有效期有限。如有问题请联系管理员。*
"""
        else:
            reply = f"""💰 已收到您的充值请求！

**金额**：{amount} 元
**支付方式**：{method_name}

由于图片上传失败，无法展示付款码，请自行前往 DeepSeek 充值页面操作：
https://platform.deepseek.com/top_up
"""

        poster = BBSPoster(self.session, self.base_url)
        success = poster.create_comment(self.token, thread_id, reply)
        if success:
            print(f"✅ 已回复帖子 {thread_id}")
        else:
            print(f"❌ 回复帖子 {thread_id} 失败")

    def process_once(self):
        """单次扫描并处理支付请求"""
        if not self.login_forum():
            return

        processed_count = 0
        poster = BBSPoster(self.session, self.base_url)

        for category_id in self.target_categories:
            threads = poster.get_threads(self.token, category_id, self.max_threads)
            if not threads:
                continue

            for thread in threads:
                thread_id = str(thread.get("id"))
                title = thread.get("title", "")
                content = thread.get("content", "") or ""

                # 检查是否包含 "@支付机器人"
                if "@支付机器人" not in title and "@支付机器人" not in content:
                    continue

                if thread_id in self.processed:
                    continue

                print(f"发现支付请求帖 {thread_id}：{title[:30]}")

                full_text = f"{title}\n{content}"
                payment_info = self.parse_payment_info(full_text)
                if not payment_info:
                    # 解析失败，回复提示
                    reply = "❌ 未能识别充值金额或支付方式，请确保帖子中包含“XX元”和“微信/支付宝”等关键词。"
                    poster.create_comment(self.token, thread_id, reply)
                else:
                    # 调用 DeepSeek 自动化模块，获取付款码截图
                    try:
                        dp = DeepSeekPayment(self.ds_username, self.ds_password)
                        # 异步执行截图
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        qrcode_bytes = loop.run_until_complete(
                            dp.generate_payment_qrcode(payment_info["amount"], payment_info["method"])
                        )
                        loop.close()
                        if qrcode_bytes:
                            self.reply_with_payment_code(thread_id, payment_info, qrcode_bytes)
                        else:
                            poster.create_comment(self.token, thread_id, "❌ 生成付款码失败，请稍后再试。")
                    except Exception as e:
                        print(f"生成付款码异常: {e}")
                        poster.create_comment(self.token, thread_id, f"❌ 生成付款码时出错: {str(e)}")

                self.processed[thread_id] = True
                self._save_processed()
                processed_count += 1
                time.sleep(2)

        print(f"本轮处理了 {processed_count} 个支付请求")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="单次运行模式")
    args = parser.parse_args()

    bot = PaymentBot()
    bot.process_once()
