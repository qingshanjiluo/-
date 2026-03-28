import requests
import time
import os
import ddddocr
import cairosvg
from io import BytesIO

class ForumLogin:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def _get_captcha(self, base_url):
        """获取验证码图片并识别"""
        try:
            # 获取验证码图片
            captcha_url = f"{base_url}/misc.php?mod=seccode&action=update&idhash=cS0&inajax=1&ajaxtarget=seccode_cS0"
            resp = self.session.get(captcha_url, timeout=10)
            # 解析返回的 HTML，提取验证码图片 URL
            import re
            match = re.search(r'<img src="(.*?)"', resp.text)
            if not match:
                return None
            img_url = match.group(1)
            if not img_url.startswith('http'):
                img_url = base_url + img_url
            img_resp = self.session.get(img_url, timeout=10)
            # 使用 ddddocr 识别验证码
            ocr = ddddocr.DdddOcr()
            # 如果是 SVG，可能需要转换
            if img_resp.headers.get('Content-Type') == 'image/svg+xml':
                # 将 SVG 转换为 PNG
                png_data = cairosvg.svg2png(bytestring=img_resp.content)
                code = ocr.classification(png_data)
            else:
                code = ocr.classification(img_resp.content)
            return code.strip()
        except Exception as e:
            print(f"验证码识别失败: {e}")
            return None

    def login(self, username, password, retries=3, base_url="https://mk48by049.mbbs.cc"):
        """
        登录论坛
        返回 (success, session, token, user_id)
        """
        for attempt in range(retries):
            try:
                # 获取登录页面，得到 formhash
                login_page = self.session.get(f"{base_url}/member.php?mod=logging&action=login")
                formhash_match = re.search(r'<input type="hidden" name="formhash" value="([^"]+)"', login_page.text)
                if not formhash_match:
                    print("未找到 formhash")
                    continue
                formhash = formhash_match.group(1)

                # 获取验证码
                seccode = self._get_captcha(base_url)
                if not seccode:
                    print("验证码获取失败")
                    continue

                # 提交登录
                login_data = {
                    'formhash': formhash,
                    'referer': base_url,
                    'loginfield': 'username',
                    'username': username,
                    'password': password,
                    'seccodeverify': seccode,
                    'questionid': 0,
                    'answer': '',
                    'cookietime': 2592000,
                }
                resp = self.session.post(
                    f"{base_url}/member.php?mod=logging&action=login&loginsubmit=yes",
                    data=login_data,
                    allow_redirects=False
                )
                if resp.status_code == 302 and 'Location' in resp.headers:
                    # 登录成功，跳转到首页
                    self.session.get(resp.headers['Location'])
                    # 获取 token（从 cookie 中提取）
                    token = None
                    for cookie in self.session.cookies:
                        if cookie.name == 'auth':
                            token = cookie.value
                            break
                    # 获取 user_id（从 cookie 或页面解析）
                    user_id = None
                    profile_resp = self.session.get(f"{base_url}/home.php?mod=space&do=profile")
                    match = re.search(r'uid=(\d+)', profile_resp.text)
                    if match:
                        user_id = match.group(1)
                    print(f"登录成功，用户ID: {user_id}")
                    return True, self.session, token, user_id
                else:
                    print(f"登录失败，状态码: {resp.status_code}")
            except Exception as e:
                print(f"登录异常 (尝试 {attempt+1}/{retries}): {e}")
            time.sleep(2)
        return False, None, None, None
