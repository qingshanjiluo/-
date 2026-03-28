import requests
import re
import ddddocr
import cairosvg
import os
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
        self.base_url = os.getenv("BASE_URL", "https://mk48by049.mbbs.cc")
        # 实际 API 基础地址
        self.api_base = "https://mbbs.zdjl.site/mk48by049.mbbs.cc"

    def _get_captcha(self):
        """获取验证码 SVG，识别后返回验证码字符串"""
        try:
            resp = self.session.get(f"{self.api_base}/bbs/login/captcha")
            if resp.status_code != 200:
                print("获取验证码失败")
                return None
            data = resp.json()
            svg_data = data.get("svg")
            if not svg_data:
                print("验证码数据为空")
                return None
            # 将 SVG 转为 PNG 并识别
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
            return False, None, None, None

        payload = {
            "username": username,
            "password": password,
            "captcha": captcha
        }
        try:
            resp = self.session.post(f"{self.api_base}/bbs/login", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    # 提取 token 和 user_id
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
        """降级使用 Playwright 自动化登录（需安装 playwright）"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("Playwright 未安装，无法降级登录")
            return False, None, None, None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            # 访问论坛首页
            page.goto(self.base_url)
            # 点击登录按钮（可能需要等待元素出现）
            try:
                page.click('button:has-text("登录")')
                page.wait_for_selector('input[name="username"]', timeout=5000)
                page.fill('input[name="username"]', username)
                page.fill('input[name="password"]', password)
                # 等待验证码图片
                captcha_img = page.wait_for_selector('img[alt="captcha"]', timeout=5000)
                # 这里需要获取验证码图片的 src，下载并识别
                img_src = captcha_img.get_attribute('src')
                # 如果 src 是 data:image，则直接提取；否则请求
                if img_src.startswith('data:image'):
                    import base64
                    img_data = base64.b64decode(img_src.split(',')[1])
                else:
                    img_data = requests.get(img_src).content
                ocr = ddddocr.DdddOcr()
                captcha = ocr.classification(img_data)
                page.fill('input[name="captcha"]', captcha)
                page.click('button:has-text("登录")')
                page.wait_for_timeout(2000)
                # 检查登录是否成功（通过URL变化或cookies）
                if "sign_in" not in page.url:
                    cookies = context.cookies()
                    token = None
                    for c in cookies:
                        if c['name'] in ('token', 'auth'):
                            token = c['value']
                            break
                    # 获取用户ID
                    user_id = None
                    if token:
                        # 通过个人主页获取uid
                        page.goto(f"{self.base_url}/home.php?mod=space")
                        match = re.search(r'uid=(\d+)', page.content())
                        if match:
                            user_id = match.group(1)
                    print(f"✅ Playwright 登录成功，用户ID: {user_id}")
                    return True, None, token, user_id  # session 暂不返回，后续用 cookie 的 session
                else:
                    print("Playwright 登录失败")
                    return False, None, None, None
            except Exception as e:
                print(f"Playwright 登录异常: {e}")
                return False, None, None, None
            finally:
                browser.close()

    def login(self, username, password, retries=3, base_url=None):
        """
        登录论坛，返回 (success, session, token, user_id)
        优先尝试 API，失败则降级 Playwright
        """
        if base_url:
            self.base_url = base_url
        for attempt in range(retries):
            print(f"登录尝试 {attempt+1}/{retries}")
            success, session, token, user_id = self._login_api(username, password)
            if success:
                return success, session, token, user_id
            print(f"API 登录失败，尝试降级 Playwright")
            success, session, token, user_id = self._login_playwright(username, password)
            if success:
                return success, session, token, user_id
            print("所有登录方式均失败，等待重试...")
            time.sleep(2)
        return False, None, None, None
