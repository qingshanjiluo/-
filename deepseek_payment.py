import asyncio
import os
from playwright.async_api import async_playwright

class DeepSeekPayment:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        """启动浏览器"""
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(headless=True)  # GitHub Actions 无头模式
        self.context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = await self.context.new_page()

    async def login(self):
        """登录 DeepSeek 平台"""
        print("🔐 正在登录 DeepSeek...")
        await self.page.goto("https://platform.deepseek.com/sign_in")
        await self.page.wait_for_load_state("networkidle")

        # 输入账号
        await self.page.fill('input[placeholder*="手机号/邮箱"]', self.username)
        # 输入密码
        await self.page.fill('input[type="password"]', self.password)
        # 点击登录按钮
        await self.page.click('button:has-text("登录")')
        await self.page.wait_for_load_state("networkidle")
        # 检查登录是否成功
        if "sign_in" in self.page.url:
            raise Exception("DeepSeek 登录失败，请检查账号密码")
        print("✅ DeepSeek 登录成功")

    async def goto_topup(self):
        """跳转到充值页面"""
        await self.page.goto("https://platform.deepseek.com/top_up")
        await self.page.wait_for_load_state("networkidle")

    async def set_amount(self, amount):
        """输入充值金额"""
        # 根据实际页面结构，可能先点击“其他金额” radio
        try:
            # 尝试点击“其他金额”选项（值为 -1 的 radio）
            await self.page.click('input[value="-1"]')
        except:
            pass
        # 填入金额
        await self.page.fill('input.ds-input__input', str(amount))

    async def select_payment_method(self, method):
        """选择支付方式：wechat 或 alipay"""
        if method == "wechat":
            await self.page.click('input[value="wechat"]')
        elif method == "alipay":
            await self.page.click('input[value="alipay"]')
        else:
            raise ValueError(f"不支持的支付方式: {method}")

    async def click_pay(self):
        """点击去支付按钮"""
        await self.page.click('div.ds-button:has-text("去支付")')
        await self.page.wait_for_timeout(3000)  # 等待弹窗出现

    async def capture_qrcode(self):
        """截取付款码区域"""
        # 等待二维码出现（可能在 canvas 或 img 中）
        # 根据之前的 inspector 记录，弹窗中有一个 canvas
        try:
            # 等待弹窗出现
            await self.page.wait_for_selector('div[role="dialog"]', timeout=10000)
            # 查找 canvas
            canvas = await self.page.query_selector('div[role="dialog"] canvas')
            if canvas:
                screenshot_bytes = await canvas.screenshot()
                return screenshot_bytes
            # 如果 canvas 未找到，尝试截图整个弹窗
            dialog = await self.page.query_selector('div[role="dialog"]')
            if dialog:
                screenshot_bytes = await dialog.screenshot()
                return screenshot_bytes
        except Exception as e:
            print(f"截图失败: {e}")
        return None

    async def close(self):
        """关闭浏览器"""
        await self.browser.close()

    async def generate_payment_qrcode(self, amount, method):
        """完整流程：登录 -> 充值 -> 截图 -> 返回图片字节"""
        await self.start()
        try:
            await self.login()
            await self.goto_topup()
            await self.set_amount(amount)
            await self.select_payment_method(method)
            await self.click_pay()
            screenshot = await self.capture_qrcode()
            return screenshot
        finally:
            await self.close()
