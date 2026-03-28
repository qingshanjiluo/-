import requests
import json
import random
import os

class DeepSeekClient:
    def __init__(self, api_key=None, base_url="https://api.deepseek.com/v1"):
        """
        初始化 DeepSeek API 客户端
        :param api_key: DeepSeek API Key，可从环境变量 DEEPSEEK_API_KEY 获取
        :param base_url: API 基础地址，默认官方 v1 端点
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量或在初始化时传入")
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })

    def generate(self, prompt, max_tokens=200, temperature=0.8, model="deepseek-chat"):
        """
        生成文本（非流式）
        :param prompt: 用户提示词
        :param max_tokens: 最大生成 token 数
        :param temperature: 随机性，0-1
        :param model: 模型名称，默认 deepseek-chat
        :return: 生成的文本字符串，失败返回空字符串
        """
        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                print(f"DeepSeek API 请求失败: {response.status_code} - {response.text}")
                return ""
        except Exception as e:
            print(f"DeepSeek API 调用异常: {e}")
            return ""

    def generate_with_system(self, system_prompt, user_prompt, max_tokens=200, temperature=0.8, model="deepseek-chat"):
        """
        带系统提示的生成
        """
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                print(f"DeepSeek API 请求失败: {response.status_code} - {response.text}")
                return ""
        except Exception as e:
            print(f"DeepSeek API 调用异常: {e}")
            return ""
