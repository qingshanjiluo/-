import requests
import re
import time
import os
import base64
import ddddocr
import cairosvg
from io import BytesIO

class ForumLogin:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'mbbs-domain': 'mk48by049.mbbs.cc',  # 关键头
        })
        # 从环境变量读取论坛地址，确保有默认值且不是空字符串
        self.base_url = os.getenv("BASE_URL", "https://mk48by049.mbbs.cc").strip()
        if not self.base_url:
            self.base_url = "https://mk48by049.mbbs.cc"
        # API 基础地址（根据 inspector 抓到的真实地址）
        self.api_base = "https://mbbs.zdjl.site/mk48by049.mbbs.cc"

    def _get_captcha(self):
        """获取验证码 SVG，识别后返回验证码字符串"""
        try:
            # 先访问首页获取必要的 cookie
            self.session.get(self.base_url, timeout=10)
            # 请求验证码
            resp = self.session.get(f"{self.api_base}/bbs/login/captcha", timeout=10)
            if resp.status_code != 200:
                print(f"获取验证码失败，HTTP {resp.status_code}")
                return None
            data = resp.json()
            svg_data = data.get("svg")
            if not svg_data:
                print("验证码数据为空，返回的 data: {data}")
                return None
            # SVG 转 PNG 并识别
            png_data = cairosvg.svg2png(bytestring=svg_data.encode('utf-8'))
            ocr = ddddocr.DdddOcr()
            code = ocr.classification(png_data)
            return code.strip()
        except Exception as e:
            print(f"验证码识别异常: {e}")
            return None

    def _login_api(self, username, password):
        """尝试 API 登录"""
        captcha = self._get_captcha()
        if not captcha:
            print("无法获取验证码，API 登录失败")
            return False, None, None, None

        payload = {
            "username": username,
            "password": password,
            "captcha": captcha
        }
        try:
            resp = self.session.post(f"{self.api_base}/bbs/login", json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    token = data.get("token") or self.session.cookies.get("token")
                    user_id = data.get("userId") or data.get("uid")
                    print(f"✅ API 登录成功，用户ID: {user_id}")
                    return True, self.session, token, user_id
                else:
                    print(f"API 登录失败: {data.get('message')}")
                    return False, None, None, None
            else:
                print(f"API 请求失败: {resp.status_code}")
                return False, None, None, None
        except Exception as e:
            print(f"API 登录异常: {e}")
            return False, None, None, None

    def _login_playwright(self, username, password):
        """降级使用 Playwright 自动化登录"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("Playwright 未安装，无法降级登录")
            return False, None, None, None

        # 确保 base_url 有效
        if not self.base_url or not self.base_url.startswith(('http://', 'https://')):
            print(f"无效的 base_url: {self.base_url}")
            return False, None, None, None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            try:
                # 访问论坛首页
                page.goto(self.base_url, timeout=15000)
                # 点击登录按钮（可能需要等待元素）
                page.click('button:has-text("登录")', timeout=10000)
                # 等待输入框出现
                page.wait_for_selector('input[name="username"]', timeout=5000)
                page.fill('input[name="username"]', username)
                page.fill('input[name="password"]', password)

                # 获取验证码图片并识别
                captcha_img = page.wait_for_selector('img[alt="captcha"]', timeout=5000)
                img_src = captcha_img.get_attribute('src')
                if img_src.startswith('data:image'):
                    # 直接解码 base64 图片
                    img_data = base64.b64decode(img_src.split(',')[1])
                else:
                    # 如果是从 URL 加载，则请求图片
                    img_resp = requests.get(img_src, timeout=10)
                    img_data = img_resp.content
                ocr = ddddocr.DdddOcr()
                captcha = ocr.classification(img_data)

                page.fill('input[name="captcha"]', captcha)
                page.click('button:has-text("登录")')
                page.wait_for_timeout(2000)

                # 检查登录是否成功
                if "sign_in" not in page.url and "login" not in page.url.lower():
                    cookies = context.cookies()
                    token = None
                    for c in cookies:
                        if c['name'] in ('token', 'auth', 'sid'):
                            token = c['value']
                            break
                    # 获取用户ID
                    user_id = None
                    if token:
                        page.goto(f"{self.base_url}/home.php?mod=space", timeout=10000)
                        match = re.search(r'uid=(\d+)', page.content())
                        if match:
                            user_id = match.group(1)
                    print(f"✅ Playwright 登录成功，用户ID: {user_id}")
                    return True, None, token, user_id
                else:
                    print("Playwright 登录失败，可能验证码错误或账号问题")
                    return False, None, None, None
            except Exception as e:
                print(f"Playwright 登录异常: {e}")
                return False, None, None, None
            finally:
                browser.close()

    def login(self, username, password, retries=3, base_url=None):
        """
        登录论坛，返回 (success, session, token, user_id)
        如果提供了 base_url，则更新 self.base_url
        """
        if base_url:
            self.base_url = base_url.strip()
        for attempt in range(retries):
            print(f"登录尝试 {attempt+1}/{retries}")
            # 尝试 API 登录
            success, session, token, user_id = self._login_api(username, password)
            if success:
                return success, session, token, user_id
            # 如果 API 失败，降级 Playwright
            print("API 登录失败，尝试降级 Playwright")
            success, session, token, user_id = self._login_playwright(username, password)
            if success:
                # 如果 playwright 成功，但 session 为空，可以返回一个新的 session（基于 cookies）
                # 这里简单返回 None，调用方可能需要重新创建 session
                return success, session, token, user_id
            print("所有登录方式均失败，等待重试...")
            time.sleep(2)
        return False, None, None, None
