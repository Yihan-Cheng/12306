"""Call one named tool through the project's configured chat model."""
import json
import os
from urllib.request import Request, urlopen


def call_tool(question, key, prompt, schema):
    base = os.getenv("CR12306_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {"model": os.getenv("CR12306_AI_MODEL", "gpt-4o-mini"),
               "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": question}],
               "tools": [{"type": "function", "function": schema}],
               "tool_choice": {"type": "function", "function": {"name": schema["name"]}}}
    request = Request(base + "/chat/completions", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urlopen(request, timeout=15) as response:
        call = json.load(response)["choices"][0]["message"]["tool_calls"][0]["function"]
    if call["name"] != schema["name"]:
        raise ValueError("unexpected tool")
    return json.loads(call["arguments"])
