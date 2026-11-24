"""Call one named tool through the project's configured chat model."""
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlparse

DEFAULT_MODEL = "gpt-4o-mini"


def call_tool(question, key, prompt, schema):
    base = os.getenv("CR12306_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {"model": os.getenv("CR12306_AI_MODEL", DEFAULT_MODEL),
               "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": question}],
               "tools": [{"type": "function", "function": schema}],
               "tool_choice": {"type": "function", "function": {"name": schema["name"]}}}
    if urlparse(base).hostname in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"}:
        payload["enable_thinking"] = False
    timeout = max(1, min(120, float(os.getenv("CR12306_AI_TIMEOUT", "45"))))
    request = Request(base + "/chat/completions", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urlopen(request, timeout=timeout) as response:
        call = json.load(response)["choices"][0]["message"]["tool_calls"][0]["function"]
    if call["name"] != schema["name"]:
        raise ValueError("unexpected tool")
    return json.loads(call["arguments"])
