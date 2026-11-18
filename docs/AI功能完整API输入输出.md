# AI 功能完整 API 输入输出

本文件记录本次重新执行的真实百炼模型请求与响应，覆盖乘客规划、四类运营报表、两种澄清、正常及异常证据解释。每个案例独立发起一次模型请求，保留完整请求体、响应 JSON、工具调用 ID、usage 和 arguments 字符串。仅认证密钥被隐藏，JSON 调整缩进。

- 采集日期为2026年11月18日，时区为 Asia/Shanghai。
- 模型为 deepseek-v4.1-flash-1017，服务为阿里云百炼兼容接口。
- 采集脚本直接调用项目业务函数，在共用 HTTP 传输处截取报文。业务查询使用本机数据库只读事务。应用输入与业务返回用于复现对应路由，其中一个案例为独立模拟证据验证。
- 真实异常采样由已登录的管理接口读取，再调用相同解释函数。缓冲采样持续更新，文档保留采集时的快照。
- 请求头列出应用显式设置的字段，认证值隐藏。HTTP 客户端自动添加的传输头不在本记录范围。

## 调用入口

| 功能 | 项目入口 | 外部模型工具 |
|---|---|---|
| 乘客行程规划 | POST /api/travel-assistant | plan_trip |
| 运营问答 | POST /api/admin/operations/query | query_operations |
| 异常解释 | POST /api/admin/anomalies/check，explain=true | explain_anomalies |
| AI 订票员 | 管理端模拟订票压测 | 当前按规则模拟乘客，无外部模型调用 |

## 案例目录

- [案例1 乘客规划：三人、席别、到达时限与价格优先](#case-1)
- [案例2 乘客规划：允许一次换乘](#case-2)
- [案例3 乘客规划：未支持条件的澄清](#case-3)
- [案例4 运营问答：订单状态分布](#case-4)
- [案例5 运营问答：已支付订单数](#case-5)
- [案例6 运营问答：候补区间排行](#case-6)
- [案例7 运营问答：缓冲请求状态分布](#case-7)
- [案例8 运营问答：未支持指标的澄清](#case-8)
- [案例9 异常解释：真实库存汇总与缓冲采样](#case-9)
- [案例10 异常解释：独立模拟异常证据](#case-10)

<a id="case-1"></a>

## 案例1 乘客规划：三人、席别、到达时限与价格优先

### 应用输入

```text
/api/travel-assistant
```

```json
{
  "question": "我们三个人10月14日从南京南去杭州东，想买二等座，晚上八点之前到，不要中转，挑便宜的。"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。"
    },
    {
      "role": "user",
      "content": "我们三个人10月14日从南京南去杭州东，想买二等座，晚上八点之前到，不要中转，挑便宜的。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "plan_trip",
        "description": "解析条件后由服务端查询演示车票",
        "parameters": {
          "type": "object",
          "properties": {
            "origin": {
              "type": "string"
            },
            "destination": {
              "type": "string"
            },
            "date": {
              "type": "string"
            },
            "people": {
              "type": "integer"
            },
            "arrive_by": {
              "type": "string"
            },
            "seat": {
              "type": "string"
            },
            "transfer": {
              "type": "string",
              "enum": [
                "direct",
                "allowed",
                "fallback"
              ]
            },
            "sort": {
              "type": "string",
              "enum": [
                "arrival",
                "price"
              ]
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "origin",
            "destination",
            "date",
            "people",
            "arrive_by",
            "seat",
            "transfer",
            "sort",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "plan_trip"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。
```

### 外部模型原始响应

HTTP状态为200，耗时5.906秒。

```json
{
  "id": "chatcmpl-e0d83b82-ecfe-9dc0-a7da-66efc3a65839",
  "object": "chat.completion",
  "created": 1795010473,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_d0aa813a059041c687473da7",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京南\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 3, \"arrive_by\": \"20:00\", \"seat\": \"二等座\", \"transfer\": \"direct\", \"sort\": \"price\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 611,
    "total_tokens": 789,
    "completion_tokens": 178,
    "prompt_tokens_details": {
      "cached_tokens": 512,
      "image_tokens": 0,
      "text_tokens": 611
    },
    "completion_tokens_details": {
      "text_tokens": 178
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "plan_trip",
  "arguments": {
    "origin": "南京南",
    "destination": "杭州东",
    "date": "2026-10-14",
    "people": 3,
    "arrive_by": "20:00",
    "seat": "二等座",
    "transfer": "direct",
    "sort": "price",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 API",
  "summary": "2026-10-14 · 南京南 → 杭州东 · 3 人 · 仅直达 · 二等座 · 20:00 前到",
  "people": 3,
  "date": "2026-10-14",
  "checked_at": "2026-11-18 22:01:20",
  "answer": "直达方案满足所选条件。",
  "ranking": "各类方案按票价排序",
  "options": [
    {
      "legs": [
        {
          "train_no": "D3239",
          "from_station_name": "南京南",
          "to_station_name": "杭州东",
          "from_station_id": 1005,
          "to_station_id": 1023,
          "run_id": 178,
          "departure_at": "2026-10-14 06:14:00",
          "arrival_at": "2026-10-14 07:24:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "84.00",
          "available_seats": "270"
        }
      ],
      "price": "84.00",
      "group_price": "252.00",
      "transfer_minutes": 0
    },
    {
      "legs": [
        {
          "train_no": "D3295",
          "from_station_name": "南京南",
          "to_station_name": "杭州东",
          "from_station_id": 1005,
          "to_station_id": 1023,
          "run_id": 182,
          "departure_at": "2026-10-14 07:51:00",
          "arrival_at": "2026-10-14 09:36:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "84.00",
          "available_seats": "270"
        }
      ],
      "price": "84.00",
      "group_price": "252.00",
      "transfer_minutes": 0
    },
    {
      "legs": [
        {
          "train_no": "D2198",
          "from_station_name": "南京南",
          "to_station_name": "杭州东",
          "from_station_id": 1005,
          "to_station_id": 1023,
          "run_id": 86,
          "departure_at": "2026-10-14 09:51:00",
          "arrival_at": "2026-10-14 11:14:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "84.00",
          "available_seats": "270"
        }
      ],
      "price": "84.00",
      "group_price": "252.00",
      "transfer_minutes": 0
    }
  ]
}
```

<a id="case-2"></a>

## 案例2 乘客规划：允许一次换乘

### 应用输入

```text
/api/travel-assistant
```

```json
{
  "question": "两个人从南通西到上海虹桥，下午3点前到，可以换乘1次。"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。"
    },
    {
      "role": "user",
      "content": "两个人从南通西到上海虹桥，下午3点前到，可以换乘1次。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "plan_trip",
        "description": "解析条件后由服务端查询演示车票",
        "parameters": {
          "type": "object",
          "properties": {
            "origin": {
              "type": "string"
            },
            "destination": {
              "type": "string"
            },
            "date": {
              "type": "string"
            },
            "people": {
              "type": "integer"
            },
            "arrive_by": {
              "type": "string"
            },
            "seat": {
              "type": "string"
            },
            "transfer": {
              "type": "string",
              "enum": [
                "direct",
                "allowed",
                "fallback"
              ]
            },
            "sort": {
              "type": "string",
              "enum": [
                "arrival",
                "price"
              ]
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "origin",
            "destination",
            "date",
            "people",
            "arrive_by",
            "seat",
            "transfer",
            "sort",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "plan_trip"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。
```

### 外部模型原始响应

HTTP状态为200，耗时14.188秒。

```json
{
  "id": "chatcmpl-2356c43a-6452-9856-b2e7-b8c671d3d6b4",
  "object": "chat.completion",
  "created": 1795010480,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_5badc28790634372975e244f",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南通西\", \"destination\": \"上海虹桥\", \"date\": \"2026-10-14\", \"people\": 2, \"arrive_by\": \"15:00\", \"seat\": \"\", \"transfer\": \"allowed\", \"sort\": \"arrival\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 602,
    "total_tokens": 779,
    "completion_tokens": 177,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 602
    },
    "completion_tokens_details": {
      "text_tokens": 177
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "plan_trip",
  "arguments": {
    "origin": "南通西",
    "destination": "上海虹桥",
    "date": "2026-10-14",
    "people": 2,
    "arrive_by": "15:00",
    "seat": "",
    "transfer": "allowed",
    "sort": "arrival",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 API",
  "summary": "2026-10-14 · 南通西 → 上海虹桥 · 2 人 · 最多换乘 1 次 · 15:00 前到",
  "people": 2,
  "date": "2026-10-14",
  "checked_at": "2026-11-18 22:01:36",
  "answer": "直达方案满足所选条件。已找到两段余票均足够的一次换乘方案。",
  "ranking": "各类方案按到达时间排序",
  "options": [
    {
      "legs": [
        {
          "train_no": "G1304",
          "from_station_name": "南通西",
          "to_station_name": "上海虹桥",
          "from_station_id": 1007,
          "to_station_id": 1003,
          "run_id": 383,
          "departure_at": "2026-10-14 08:59:00",
          "arrival_at": "2026-10-14 10:16:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "95.00",
          "available_seats": "180"
        }
      ],
      "price": "95.00",
      "group_price": "190.00",
      "transfer_minutes": 0
    },
    {
      "legs": [
        {
          "train_no": "D3125",
          "from_station_name": "南通西",
          "to_station_name": "上海虹桥",
          "from_station_id": 1007,
          "to_station_id": 1003,
          "run_id": 148,
          "departure_at": "2026-10-14 09:08:00",
          "arrival_at": "2026-10-14 10:25:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "79.00",
          "available_seats": "269"
        }
      ],
      "price": "79.00",
      "group_price": "158.00",
      "transfer_minutes": 0
    },
    {
      "legs": [
        {
          "train_no": "C3795",
          "from_station_name": "南通西",
          "to_station_name": "上海虹桥",
          "from_station_id": 1007,
          "to_station_id": 1003,
          "run_id": 48,
          "departure_at": "2026-10-14 09:25:00",
          "arrival_at": "2026-10-14 10:50:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "95.00",
          "available_seats": "180"
        }
      ],
      "price": "95.00",
      "group_price": "190.00",
      "transfer_minutes": 0
    },
    {
      "legs": [
        {
          "train_no": "G1304",
          "run_id": 383,
          "departure_at": "2026-10-14 08:59:00",
          "arrival_at": "2026-10-14 10:46:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "135.50",
          "available_seats": 180,
          "from_station_name": "南通西",
          "to_station_name": "嘉兴南",
          "from_station_id": 1007,
          "to_station_id": 1020
        },
        {
          "train_no": "G7506",
          "run_id": 1229,
          "departure_at": "2026-10-14 11:08:00",
          "arrival_at": "2026-10-14 11:36:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "40.50",
          "available_seats": 180,
          "from_station_name": "嘉兴南",
          "to_station_name": "上海虹桥",
          "from_station_id": 1020,
          "to_station_id": 1003
        }
      ],
      "price": "176.00",
      "group_price": "352.00",
      "transfer_minutes": 22
    },
    {
      "legs": [
        {
          "train_no": "G1304",
          "run_id": 383,
          "departure_at": "2026-10-14 08:59:00",
          "arrival_at": "2026-10-14 10:46:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "135.50",
          "available_seats": 180,
          "from_station_name": "南通西",
          "to_station_name": "嘉兴南",
          "from_station_id": 1007,
          "to_station_id": 1020
        },
        {
          "train_no": "D3324",
          "run_id": 187,
          "departure_at": "2026-10-14 11:01:00",
          "arrival_at": "2026-10-14 11:41:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "33.50",
          "available_seats": 270,
          "from_station_name": "嘉兴南",
          "to_station_name": "上海虹桥",
          "from_station_id": 1020,
          "to_station_id": 1003
        }
      ],
      "price": "169.00",
      "group_price": "338.00",
      "transfer_minutes": 15
    },
    {
      "legs": [
        {
          "train_no": "D3125",
          "run_id": 148,
          "departure_at": "2026-10-14 09:08:00",
          "arrival_at": "2026-10-14 10:57:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "113.00",
          "available_seats": 269,
          "from_station_name": "南通西",
          "to_station_name": "嘉兴南",
          "from_station_id": 1007,
          "to_station_id": 1020
        },
        {
          "train_no": "G7586",
          "run_id": 1292,
          "departure_at": "2026-10-14 11:18:00",
          "arrival_at": "2026-10-14 11:46:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "40.50",
          "available_seats": 180,
          "from_station_name": "嘉兴南",
          "to_station_name": "上海虹桥",
          "from_station_id": 1020,
          "to_station_id": 1003
        }
      ],
      "price": "153.50",
      "group_price": "307.00",
      "transfer_minutes": 21
    }
  ]
}
```

<a id="case-3"></a>

## 案例3 乘客规划：未支持条件的澄清

### 应用输入

```text
/api/travel-assistant
```

```json
{
  "question": "10月14日从南京去上海，预算不超过30元。"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。"
    },
    {
      "role": "user",
      "content": "10月14日从南京去上海，预算不超过30元。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "plan_trip",
        "description": "解析条件后由服务端查询演示车票",
        "parameters": {
          "type": "object",
          "properties": {
            "origin": {
              "type": "string"
            },
            "destination": {
              "type": "string"
            },
            "date": {
              "type": "string"
            },
            "people": {
              "type": "integer"
            },
            "arrive_by": {
              "type": "string"
            },
            "seat": {
              "type": "string"
            },
            "transfer": {
              "type": "string",
              "enum": [
                "direct",
                "allowed",
                "fallback"
              ]
            },
            "sort": {
              "type": "string",
              "enum": [
                "arrival",
                "price"
              ]
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "origin",
            "destination",
            "date",
            "people",
            "arrive_by",
            "seat",
            "transfer",
            "sort",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "plan_trip"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
提取铁路购票条件。默认日期 2026-10-14、1人、优先直达。保留地名及站/市后缀。date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。超过1次的换乘需求用 clarify 提示目前最多支持1次。arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。价格优先用 price，其他用 arrival。不要编造地点或票务信息。缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，在 clarify 写简短中文追问，不要忽略条件。
```

### 外部模型原始响应

HTTP状态为200，耗时11.609秒。

```json
{
  "id": "chatcmpl-42b0482e-4a5d-9f92-bd25-0e17ead1250e",
  "object": "chat.completion",
  "created": 1795010495,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_b08d72f8642e476dba18a905",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京\", \"destination\": \"上海\", \"date\": \"2026-10-14\", \"people\": 1, \"arrive_by\": \"\", \"seat\": \"\", \"transfer\": \"direct\", \"sort\": \"price\", \"clarify\": \"预算上限（不超过30元）目前无法作为筛选条件表达，是否需要我按价格从低到高查询直达车次供你参考？\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 595,
    "total_tokens": 795,
    "completion_tokens": 200,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 595
    },
    "completion_tokens_details": {
      "text_tokens": 200
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "plan_trip",
  "arguments": {
    "origin": "南京",
    "destination": "上海",
    "date": "2026-10-14",
    "people": 1,
    "arrive_by": "",
    "seat": "",
    "transfer": "direct",
    "sort": "price",
    "clarify": "预算上限（不超过30元）目前无法作为筛选条件表达，是否需要我按价格从低到高查询直达车次供你参考？"
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 API",
  "answer": "预算上限（不超过30元）目前无法作为筛选条件表达，是否需要我按价格从低到高查询直达车次供你参考？",
  "options": []
}
```

<a id="case-4"></a>

## 案例4 运营问答：订单状态分布

### 应用输入

```text
/api/admin/operations/query
```

```json
{
  "question": "麻烦按各个状态统计一下G1304的订单分别有多少笔，运营日2026-10-14。",
  "serviceDate": "2026-10-14"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。\nSELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s AND train_no = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 10\n\n订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。\nSELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20\n\n已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。\nSELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nAND order_status = 'PAID'\nLIMIT 20\n\n缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。\nSELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s AND train_no = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20"
    },
    {
      "role": "user",
      "content": "麻烦按各个状态统计一下G1304的订单分别有多少笔，运营日2026-10-14。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "query_operations",
        "description": "生成只读报表 SQL 或提出澄清",
        "parameters": {
          "type": "object",
          "properties": {
            "sql": {
              "type": "string"
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "sql",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "query_operations"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。
候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。
SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments
WHERE service_date = %s AND train_no = %s
ORDER BY waiting_people DESC, train_no, origin, destination
LIMIT 10

订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s AND train_no = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20

已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。
SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders
WHERE service_date = %s AND train_no = %s
AND order_status = 'PAID'
LIMIT 20

缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。
SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer
WHERE service_date = %s AND train_no = %s
GROUP BY request_status ORDER BY request_count DESC, request_status
LIMIT 20
```

### 外部模型原始响应

HTTP状态为200，耗时23.625秒。

```json
{
  "id": "chatcmpl-6d759c2d-9495-948a-8b45-7c679eef1971",
  "object": "chat.completion",
  "created": 1795010507,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_ba55a59f524143eeaaaf94b1",
            "type": "function",
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\\nWHERE service_date = %s AND train_no = %s\\nGROUP BY order_status ORDER BY orders DESC, order_status\\nLIMIT 20\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 783,
    "total_tokens": 884,
    "completion_tokens": 101,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 783
    },
    "completion_tokens_details": {
      "text_tokens": 101
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "query_operations",
  "arguments": {
    "sql": "SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 NL2SQL",
  "scope": "运营日 2026-10-14 · G1304",
  "title": "订单状态分布",
  "answer": "已退款 3 笔。",
  "definition": "按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。",
  "columns": [
    [
      "order_status",
      "订单状态"
    ],
    [
      "orders",
      "订单数"
    ]
  ],
  "rows": [
    {
      "order_status": "REFUNDED",
      "orders": 3
    }
  ],
  "sql": "SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20",
  "params": [
    "2026-10-14",
    "G1304"
  ],
  "checked_at": "2026-11-18T14:02:11+00:00"
}
```

执行时使用的绑定参数

```json
[
  "2026-10-14",
  "G1304"
]
```

<a id="case-5"></a>

## 案例5 运营问答：已支付订单数

### 应用输入

```text
/api/admin/operations/query
```

```json
{
  "question": "2026-10-14这天G1304已经支付了多少笔订单？",
  "serviceDate": "2026-10-14"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。\nSELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s AND train_no = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 10\n\n订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。\nSELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20\n\n已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。\nSELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nAND order_status = 'PAID'\nLIMIT 20\n\n缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。\nSELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s AND train_no = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20"
    },
    {
      "role": "user",
      "content": "2026-10-14这天G1304已经支付了多少笔订单？"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "query_operations",
        "description": "生成只读报表 SQL 或提出澄清",
        "parameters": {
          "type": "object",
          "properties": {
            "sql": {
              "type": "string"
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "sql",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "query_operations"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。
候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。
SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments
WHERE service_date = %s AND train_no = %s
ORDER BY waiting_people DESC, train_no, origin, destination
LIMIT 10

订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s AND train_no = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20

已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。
SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders
WHERE service_date = %s AND train_no = %s
AND order_status = 'PAID'
LIMIT 20

缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。
SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer
WHERE service_date = %s AND train_no = %s
GROUP BY request_status ORDER BY request_count DESC, request_status
LIMIT 20
```

### 外部模型原始响应

HTTP状态为200，耗时18.266秒。

```json
{
  "id": "chatcmpl-6876071c-8e64-9bbc-a748-5eaa0dac99d3",
  "object": "chat.completion",
  "created": 1795010530,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_07b12337d3a7450b96117b87",
            "type": "function",
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\\nWHERE service_date = %s AND train_no = %s\\nAND order_status = 'PAID'\\nLIMIT 20\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 775,
    "total_tokens": 872,
    "completion_tokens": 97,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 775
    },
    "completion_tokens_details": {
      "text_tokens": 97
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "query_operations",
  "arguments": {
    "sql": "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nAND order_status = 'PAID'\nLIMIT 20",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 NL2SQL",
  "scope": "运营日 2026-10-14 · G1304",
  "title": "已支付订单数",
  "answer": "当前已支付订单共 0 笔。",
  "definition": "仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。",
  "columns": [
    [
      "paid_orders",
      "已支付订单数"
    ]
  ],
  "rows": [
    {
      "paid_orders": 0
    }
  ],
  "sql": "SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s AND train_no = %s\nAND order_status = 'PAID'\nLIMIT 20",
  "params": [
    "2026-10-14",
    "G1304"
  ],
  "checked_at": "2026-11-18T14:02:29+00:00"
}
```

执行时使用的绑定参数

```json
[
  "2026-10-14",
  "G1304"
]
```

<a id="case-6"></a>

## 案例6 运营问答：候补区间排行

### 应用输入

```text
/api/admin/operations/query
```

```json
{
  "question": "查查2026-10-14全网候补区间排名，给我前3名。",
  "serviceDate": "2026-10-14"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。\nSELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 3"
    },
    {
      "role": "user",
      "content": "查查2026-10-14全网候补区间排名，给我前3名。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "query_operations",
        "description": "生成只读报表 SQL 或提出澄清",
        "parameters": {
          "type": "object",
          "properties": {
            "sql": {
              "type": "string"
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "sql",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "query_operations"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。
候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。
SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments
WHERE service_date = %s
ORDER BY waiting_people DESC, train_no, origin, destination
LIMIT 3
```

### 外部模型原始响应

HTTP状态为200，耗时9.453秒。

```json
{
  "id": "chatcmpl-59f3a9ae-c908-9bac-a7b5-0ad87ef7b549",
  "object": "chat.completion",
  "created": 1795010549,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_94ef8b395674485ebb5902fb",
            "type": "function",
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\\nWHERE service_date = %s\\nORDER BY waiting_people DESC, train_no, origin, destination\\nLIMIT 3\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 540,
    "total_tokens": 642,
    "completion_tokens": 102,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 540
    },
    "completion_tokens_details": {
      "text_tokens": 102
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "query_operations",
  "arguments": {
    "sql": "SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 3",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 NL2SQL",
  "scope": "运营日 2026-10-14 · 全部车次",
  "title": "候补区间排行",
  "answer": "该范围内没有正在排队或匹配的候补请求。",
  "definition": "按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。",
  "columns": [
    [
      "train_no",
      "车次"
    ],
    [
      "origin",
      "上车站"
    ],
    [
      "destination",
      "下车站"
    ],
    [
      "waiting_people",
      "候补人数"
    ],
    [
      "second_seats",
      "二等座余票"
    ]
  ],
  "rows": [],
  "sql": "SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 3",
  "params": [
    "2026-10-14"
  ],
  "checked_at": "2026-11-18T14:02:39+00:00"
}
```

执行时使用的绑定参数

```json
[
  "2026-10-14"
]
```

<a id="case-7"></a>

## 案例7 运营问答：缓冲请求状态分布

### 应用输入

```text
/api/admin/operations/query
```

```json
{
  "question": "缓冲请求状态分布",
  "serviceDate": "2026-10-14"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。\nSELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 10\n\n订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。\nSELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20\n\n已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。\nSELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s\nAND order_status = 'PAID'\nLIMIT 20\n\n缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。\nSELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20"
    },
    {
      "role": "user",
      "content": "缓冲请求状态分布"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "query_operations",
        "description": "生成只读报表 SQL 或提出澄清",
        "parameters": {
          "type": "object",
          "properties": {
            "sql": {
              "type": "string"
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "sql",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "query_operations"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。
候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。
SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments
WHERE service_date = %s
ORDER BY waiting_people DESC, train_no, origin, destination
LIMIT 10

订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20

已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。
SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders
WHERE service_date = %s
AND order_status = 'PAID'
LIMIT 20

缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。
SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer
WHERE service_date = %s
GROUP BY request_status ORDER BY request_count DESC, request_status
LIMIT 20
```

### 外部模型原始响应

HTTP状态为200，耗时7.86秒。

```json
{
  "id": "chatcmpl-adf43a2d-c4c0-94a6-91fa-30aeeae8be3c",
  "object": "chat.completion",
  "created": 1795010558,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_955ac9cae4ae40ad9605e9b5",
            "type": "function",
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\\nWHERE service_date = %s\\nGROUP BY request_status ORDER BY request_count DESC, request_status\\nLIMIT 20\", \"clarify\": \"\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 739,
    "total_tokens": 833,
    "completion_tokens": 94,
    "prompt_tokens_details": {
      "cached_tokens": 512,
      "image_tokens": 0,
      "text_tokens": 739
    },
    "completion_tokens_details": {
      "text_tokens": 94
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "query_operations",
  "arguments": {
    "sql": "SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20",
    "clarify": ""
  }
}
```

### 后端业务函数完整返回

```json
{
  "mode": "模型 NL2SQL",
  "scope": "运营日 2026-10-14 · 全部车次",
  "title": "缓冲请求状态分布",
  "answer": "已成功 6 条，已失败 3 条。",
  "definition": "按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。",
  "columns": [
    [
      "request_status",
      "缓冲状态"
    ],
    [
      "request_count",
      "请求数"
    ]
  ],
  "rows": [
    {
      "request_status": "SUCCEEDED",
      "request_count": "6"
    },
    {
      "request_status": "FAILED",
      "request_count": "3"
    }
  ],
  "sql": "SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20",
  "params": [
    "2026-10-14"
  ],
  "checked_at": "2026-11-18T14:02:47+00:00"
}
```

执行时使用的绑定参数

```json
[
  "2026-10-14"
]
```

<a id="case-8"></a>

## 案例8 运营问答：未支持指标的澄清

### 应用输入

```text
/api/admin/operations/query
```

```json
{
  "question": "2026-10-14哪个车次退票率最高？",
  "serviceDate": "2026-10-14"
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。\nSELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments\nWHERE service_date = %s\nORDER BY waiting_people DESC, train_no, origin, destination\nLIMIT 1\n\n订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。\nSELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20\n\n已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。\nSELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders\nWHERE service_date = %s\nAND order_status = 'PAID'\nLIMIT 20\n\n缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。\nSELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer\nWHERE service_date = %s\nGROUP BY request_status ORDER BY request_count DESC, request_status\nLIMIT 20"
    },
    {
      "role": "user",
      "content": "2026-10-14哪个车次退票率最高？"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "query_operations",
        "description": "生成只读报表 SQL 或提出澄清",
        "parameters": {
          "type": "object",
          "properties": {
            "sql": {
              "type": "string"
            },
            "clarify": {
              "type": "string"
            }
          },
          "required": [
            "sql",
            "clarify"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "query_operations"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。页面已选择运营日 2026-10-14，问题中明确的日期也已由后端处理。车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。
候补区间排行。按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。人数相同时按车次、上下车站排序。
SELECT train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments
WHERE service_date = %s
ORDER BY waiting_people DESC, train_no, origin, destination
LIMIT 1

订单状态分布。按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20

已支付订单数。仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。
SELECT COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders
WHERE service_date = %s
AND order_status = 'PAID'
LIMIT 20

缓冲请求状态分布。按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。
SELECT request_status, SUM(requests) AS request_count FROM v_ops_buffer
WHERE service_date = %s
GROUP BY request_status ORDER BY request_count DESC, request_status
LIMIT 20
```

### 外部模型原始响应

HTTP状态为200，耗时11.375秒。

```json
{
  "id": "chatcmpl-bbd24ba0-6826-9b0c-b428-ddb0e4f99d6b",
  "object": "chat.completion",
  "created": 1795010566,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_f72acb23c30844d2aeda071e",
            "type": "function",
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"\", \"clarify\": \"当前可支持的指标只有：候补区间排行、订单状态分布、已支付订单数、缓冲请求状态分布。没有“按车次统计退票数量/退票率”的口径（退票率还需明确分母：支付订单数、购票张数还是订票请求数），因此无法生成该 SQL。\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 749,
    "total_tokens": 870,
    "completion_tokens": 121,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 749
    },
    "completion_tokens_details": {
      "text_tokens": 121
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "query_operations",
  "arguments": {
    "sql": "",
    "clarify": "当前可支持的指标只有：候补区间排行、订单状态分布、已支付订单数、缓冲请求状态分布。没有“按车次统计退票数量/退票率”的口径（退票率还需明确分母：支付订单数、购票张数还是订票请求数），因此无法生成该 SQL。"
  }
}
```

### 后端业务函数完整返回

```json
{
  "clarify": "当前可支持的指标只有：候补区间排行、订单状态分布、已支付订单数、缓冲请求状态分布。没有“按车次统计退票数量/退票率”的口径（退票率还需明确分母：支付订单数、购票张数还是订票请求数），因此无法生成该 SQL。",
  "mode": "模型 NL2SQL"
}
```

<a id="case-9"></a>

## 案例9 异常解释：真实库存汇总与缓冲采样

### 应用输入

```text
/api/admin/anomalies/check
```

```json
{
  "date": "2026-10-14",
  "train": "G8359",
  "explain": true
}
```

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "你是铁路运营诊断助手。仅据证据解释规则状态和建议人工核查的方向。库存日期是固定演示班次运营日，缓冲覆盖全库并按当前真实时间采样，两者时间范围独立。缓冲样本直接SELECT数据库取得；采样失败或过期会显示unavailable，有效样本均为0表示数据库中没有对应状态的请求。mask_mismatch_count是两份位图不同的座位数，overlap_seat_count是重叠分配座位数，anomaly_count是两者并集，禁止将其等同于所有位图不一致。保持检测结果，推测必须标明待验证。不要编造故障原因、数字或已完成的修复。用简短中文回复，最多500字。"
    },
    {
      "role": "user",
      "content": "{\"scope\": \"2026-10-14 · G8359 库存；全库订票缓冲\", \"inventory\": {\"status\": \"normal\", \"mask_mismatch_count\": 0, \"overlap_seat_count\": 0, \"checked_seats\": 218, \"anomaly_count\": 0, \"definition\": \"同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。\"}, \"buffer\": {\"samples\": [{\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:13.784303\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:18.786557\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:23.789287\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:28.792586\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:33.795274\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:38.798200\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:43.799204\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:48.802154\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:53.805201\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:00:58.808169\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:01:03.810812\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:01:08.814251\"}, {\"queued\": 0, \"processing\": 0, \"oldest_seconds\": 0, \"expired_leases\": 0, \"retried\": 0, \"captured_at\": \"2026-11-18 22:01:13.813900\"}], \"interval_seconds\": 5, \"window_seconds\": 10, \"definition\": \"全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。\", \"status\": \"normal\", \"message\": \"最近3次采样未触发持续积压规则。\"}}"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "explain_anomalies",
        "description": "解释已经由程序判定的检测结果",
        "parameters": {
          "type": "object",
          "properties": {
            "explanation": {
              "type": "string"
            }
          },
          "required": [
            "explanation"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "explain_anomalies"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
你是铁路运营诊断助手。仅据证据解释规则状态和建议人工核查的方向。库存日期是固定演示班次运营日，缓冲覆盖全库并按当前真实时间采样，两者时间范围独立。缓冲样本直接SELECT数据库取得；采样失败或过期会显示unavailable，有效样本均为0表示数据库中没有对应状态的请求。mask_mismatch_count是两份位图不同的座位数，overlap_seat_count是重叠分配座位数，anomaly_count是两者并集，禁止将其等同于所有位图不一致。保持检测结果，推测必须标明待验证。不要编造故障原因、数字或已完成的修复。用简短中文回复，最多500字。
```

### 外部模型原始响应

HTTP状态为200，耗时12.485秒。

```json
{
  "id": "chatcmpl-0fb54a88-2d83-9bf7-8eda-4f484bd94399",
  "object": "chat.completion",
  "created": 1795010577,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_dce97fb611aa45a0add77a6c",
            "type": "function",
            "function": {
              "name": "explain_anomalies",
              "arguments": "{\"explanation\": \"2026-10-14 班次 G8359 库存检测：位图不一致 0、重叠分配 0、anomaly_count 0（已检查 218 座），状态 normal，未发现异常。全库订票缓冲 13 次有效采样（每 5 秒，覆盖约 60 秒），queued/processing/expired_leases/retried 均为 0，oldest_seconds 恒为 0，未触发持续积压规则，状态 normal。注意：库存日期属固定演示班次运营日，缓冲采样时间为 2026-11-18 22:00–22:01，两者时间范围独立，不构成同期证据。建议人工核查方向（待验证）：确认演示数据快照与真实库一致性，以及长时间零请求是否符合预期（可能是演示环境无流量，也可能采样口径问题需核对）。\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 1440,
    "total_tokens": 1671,
    "completion_tokens": 231,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 1440
    },
    "completion_tokens_details": {
      "text_tokens": 231
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "explain_anomalies",
  "arguments": {
    "explanation": "2026-10-14 班次 G8359 库存检测：位图不一致 0、重叠分配 0、anomaly_count 0（已检查 218 座），状态 normal，未发现异常。全库订票缓冲 13 次有效采样（每 5 秒，覆盖约 60 秒），queued/processing/expired_leases/retried 均为 0，oldest_seconds 恒为 0，未触发持续积压规则，状态 normal。注意：库存日期属固定演示班次运营日，缓冲采样时间为 2026-11-18 22:00–22:01，两者时间范围独立，不构成同期证据。建议人工核查方向（待验证）：确认演示数据快照与真实库一致性，以及长时间零请求是否符合预期（可能是演示环境无流量，也可能采样口径问题需核对）。"
  }
}
```

### 后端业务函数完整返回

```json
{
  "scope": "2026-10-14 · G8359 库存；全库订票缓冲",
  "checked_at": "2026-11-18T14:01:13+00:00",
  "inventory": {
    "status": "normal",
    "mask_mismatch_count": 0,
    "overlap_seat_count": 0,
    "checked_seats": 218,
    "anomaly_count": 0,
    "findings": [],
    "definition": "同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
  },
  "buffer": {
    "samples": [
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:13.784303"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:18.786557"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:23.789287"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:28.792586"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:33.795274"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:38.798200"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:43.799204"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:48.802154"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:53.805201"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:00:58.808169"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:01:03.810812"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:01:08.814251"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-18 22:01:13.813900"
      }
    ],
    "interval_seconds": 5,
    "window_seconds": 10,
    "definition": "全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。",
    "status": "normal",
    "message": "最近3次采样未触发持续积压规则。"
  },
  "explanation": {
    "mode": "模型辅助解释（建议需人工核查）",
    "text": "2026-10-14 班次 G8359 库存检测：位图不一致 0、重叠分配 0、anomaly_count 0（已检查 218 座），状态 normal，未发现异常。全库订票缓冲 13 次有效采样（每 5 秒，覆盖约 60 秒），queued/processing/expired_leases/retried 均为 0，oldest_seconds 恒为 0，未触发持续积压规则，状态 normal。注意：库存日期属固定演示班次运营日，缓冲采样时间为 2026-11-18 22:00–22:01，两者时间范围独立，不构成同期证据。建议人工核查方向（待验证）：确认演示数据快照与真实库一致性，以及长时间零请求是否符合预期（可能是演示环境无流量，也可能采样口径问题需核对）。"
  }
}
```

<a id="case-10"></a>

## 案例10 异常解释：独立模拟异常证据

### 应用输入

```text
采集脚本调用 anomalies.explain_report(demo_anomalies())
```

```json
{
  "source": "模拟证据样本，独立于业务数据",
  "scope": "模拟库存与模拟缓冲",
  "checked_at": "2026-11-18T14:03:11+00:00",
  "inventory": {
    "status": "anomaly",
    "mask_mismatch_count": 1,
    "overlap_seat_count": 1,
    "checked_seats": 2,
    "anomaly_count": 2,
    "findings": [
      {
        "run_id": 0,
        "seat_id": 1,
        "carriage_no": 1,
        "seat_no": "01A",
        "actual_mask": "3",
        "expected_mask": "1",
        "differing_segments": [
          2
        ],
        "overlapping_allocations": false
      },
      {
        "run_id": 0,
        "seat_id": 2,
        "carriage_no": 1,
        "seat_no": "01B",
        "actual_mask": "7",
        "expected_mask": "7",
        "differing_segments": [],
        "overlapping_allocations": true
      }
    ],
    "definition": "同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
  },
  "buffer": {
    "samples": [
      {
        "captured_at": "模拟第0秒",
        "queued": 2,
        "oldest_seconds": 10,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      },
      {
        "captured_at": "模拟第5秒",
        "queued": 4,
        "oldest_seconds": 15,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      },
      {
        "captured_at": "模拟第10秒",
        "queued": 7,
        "oldest_seconds": 20,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      }
    ],
    "interval_seconds": 5,
    "window_seconds": 10,
    "definition": "全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。",
    "status": "anomaly",
    "message": "最近3次采样满足持续积压规则。"
  },
  "explanation": {
    "mode": "样本说明",
    "text": "01A库存位图多占用了第2个区段；01B有重叠的有效分配。模拟缓冲连续3次排队数和最老等待时间上升，触发持续积压规则。"
  }
}
```

该案例使用独立模拟样本调用解释函数，模型返回为真实 API 响应。页面 GET /api/admin/anomalies/demo 本身返回固定样本说明，外部模型调用由本次采集脚本发起。

### 外部模型请求

```text
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

应用请求头

```json
{
  "Content-type": "application/json",
  "Authorization": "Bearer [密钥已隐藏]"
}
```

请求超时设置为45.0秒。

```json
{
  "model": "deepseek-v4.1-flash-1017",
  "messages": [
    {
      "role": "system",
      "content": "你是铁路运营诊断助手。仅据证据解释规则状态和建议人工核查的方向。库存日期是固定演示班次运营日，缓冲覆盖全库并按当前真实时间采样，两者时间范围独立。缓冲样本直接SELECT数据库取得；采样失败或过期会显示unavailable，有效样本均为0表示数据库中没有对应状态的请求。mask_mismatch_count是两份位图不同的座位数，overlap_seat_count是重叠分配座位数，anomaly_count是两者并集，禁止将其等同于所有位图不一致。保持检测结果，推测必须标明待验证。不要编造故障原因、数字或已完成的修复。用简短中文回复，最多500字。"
    },
    {
      "role": "user",
      "content": "{\"scope\": \"模拟库存与模拟缓冲\", \"inventory\": {\"status\": \"anomaly\", \"mask_mismatch_count\": 1, \"overlap_seat_count\": 1, \"checked_seats\": 2, \"anomaly_count\": 2, \"definition\": \"同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。\"}, \"buffer\": {\"samples\": [{\"captured_at\": \"模拟第0秒\", \"queued\": 2, \"oldest_seconds\": 10, \"processing\": 1, \"expired_leases\": 0, \"retried\": 0}, {\"captured_at\": \"模拟第5秒\", \"queued\": 4, \"oldest_seconds\": 15, \"processing\": 1, \"expired_leases\": 0, \"retried\": 0}, {\"captured_at\": \"模拟第10秒\", \"queued\": 7, \"oldest_seconds\": 20, \"processing\": 1, \"expired_leases\": 0, \"retried\": 0}], \"interval_seconds\": 5, \"window_seconds\": 10, \"definition\": \"全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。\", \"status\": \"anomaly\", \"message\": \"最近3次采样满足持续积压规则。\"}}"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "explain_anomalies",
        "description": "解释已经由程序判定的检测结果",
        "parameters": {
          "type": "object",
          "properties": {
            "explanation": {
              "type": "string"
            }
          },
          "required": [
            "explanation"
          ],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": {
    "type": "function",
    "function": {
      "name": "explain_anomalies"
    }
  },
  "enable_thinking": false
}
```

系统提示词按实际换行展开如下，内容与请求体的 system 消息一致。

```text
你是铁路运营诊断助手。仅据证据解释规则状态和建议人工核查的方向。库存日期是固定演示班次运营日，缓冲覆盖全库并按当前真实时间采样，两者时间范围独立。缓冲样本直接SELECT数据库取得；采样失败或过期会显示unavailable，有效样本均为0表示数据库中没有对应状态的请求。mask_mismatch_count是两份位图不同的座位数，overlap_seat_count是重叠分配座位数，anomaly_count是两者并集，禁止将其等同于所有位图不一致。保持检测结果，推测必须标明待验证。不要编造故障原因、数字或已完成的修复。用简短中文回复，最多500字。
```

### 外部模型原始响应

HTTP状态为200，耗时18.5秒。

```json
{
  "id": "chatcmpl-55d5ddd2-fd5f-9e28-985e-caab9b685bf3",
  "object": "chat.completion",
  "created": 1795010590,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "reasoning_content": "",
        "content": "",
        "tool_calls": [
          {
            "id": "call_48d61ef592e74368abefd008",
            "type": "function",
            "function": {
              "name": "explain_anomalies",
              "arguments": "{\"explanation\": \"库存侧：同一只读快照中核对 HOLD/CONFIRMED 分配区间按位或与库存位图，2个受检座位中 mask_mismatch_count=1（位图不一致）、overlap_seat_count=1（重叠分配），anomaly_count=2为两者并集，说明这两类问题各命中1个座位、无叠加；不表示全部位图不一致，也不代表成因。缓冲侧：模拟第0/5/10秒三次采样，queued 2→4→7、oldest_seconds 10→15→20均单调增加，最老请求已等待≥10秒，processing 与 retried 未见变化，符合持续积压规则。以上为检测结果，故障原因未确认。建议人工核查：该快照中不一致座位与重叠座位的具体座位号和分配来源；排队增长是否与前置处理受阻或下游响应变慢相关（待验证），最早排队请求的租约与重试情况。\"}"
            },
            "index": 0
          }
        ]
      },
      "finish_reason": "tool_calls",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 797,
    "total_tokens": 1047,
    "completion_tokens": 250,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 797
    },
    "completion_tokens_details": {
      "text_tokens": 250
    }
  }
}
```

工具参数解析后的完整对象

```json
{
  "name": "explain_anomalies",
  "arguments": {
    "explanation": "库存侧：同一只读快照中核对 HOLD/CONFIRMED 分配区间按位或与库存位图，2个受检座位中 mask_mismatch_count=1（位图不一致）、overlap_seat_count=1（重叠分配），anomaly_count=2为两者并集，说明这两类问题各命中1个座位、无叠加；不表示全部位图不一致，也不代表成因。缓冲侧：模拟第0/5/10秒三次采样，queued 2→4→7、oldest_seconds 10→15→20均单调增加，最老请求已等待≥10秒，processing 与 retried 未见变化，符合持续积压规则。以上为检测结果，故障原因未确认。建议人工核查：该快照中不一致座位与重叠座位的具体座位号和分配来源；排队增长是否与前置处理受阻或下游响应变慢相关（待验证），最早排队请求的租约与重试情况。"
  }
}
```

### 后端业务函数完整返回

```json
{
  "source": "模拟证据样本，独立于业务数据",
  "scope": "模拟库存与模拟缓冲",
  "checked_at": "2026-11-18T14:03:11+00:00",
  "inventory": {
    "status": "anomaly",
    "mask_mismatch_count": 1,
    "overlap_seat_count": 1,
    "checked_seats": 2,
    "anomaly_count": 2,
    "findings": [
      {
        "run_id": 0,
        "seat_id": 1,
        "carriage_no": 1,
        "seat_no": "01A",
        "actual_mask": "3",
        "expected_mask": "1",
        "differing_segments": [
          2
        ],
        "overlapping_allocations": false
      },
      {
        "run_id": 0,
        "seat_id": 2,
        "carriage_no": 1,
        "seat_no": "01B",
        "actual_mask": "7",
        "expected_mask": "7",
        "differing_segments": [],
        "overlapping_allocations": true
      }
    ],
    "definition": "同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
  },
  "buffer": {
    "samples": [
      {
        "captured_at": "模拟第0秒",
        "queued": 2,
        "oldest_seconds": 10,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      },
      {
        "captured_at": "模拟第5秒",
        "queued": 4,
        "oldest_seconds": 15,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      },
      {
        "captured_at": "模拟第10秒",
        "queued": 7,
        "oldest_seconds": 20,
        "processing": 1,
        "expired_leases": 0,
        "retried": 0
      }
    ],
    "interval_seconds": 5,
    "window_seconds": 10,
    "definition": "全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。",
    "status": "anomaly",
    "message": "最近3次采样满足持续积压规则。"
  },
  "explanation": {
    "mode": "模型辅助解释（建议需人工核查）",
    "text": "库存侧：同一只读快照中核对 HOLD/CONFIRMED 分配区间按位或与库存位图，2个受检座位中 mask_mismatch_count=1（位图不一致）、overlap_seat_count=1（重叠分配），anomaly_count=2为两者并集，说明这两类问题各命中1个座位、无叠加；不表示全部位图不一致，也不代表成因。缓冲侧：模拟第0/5/10秒三次采样，queued 2→4→7、oldest_seconds 10→15→20均单调增加，最老请求已等待≥10秒，processing 与 retried 未见变化，符合持续积压规则。以上为检测结果，故障原因未确认。建议人工核查：该快照中不一致座位与重叠座位的具体座位号和分配来源；排队增长是否与前置处理受阻或下游响应变慢相关（待验证），最早排队请求的租约与重试情况。"
  }
}
```

## 读取本记录时的口径

乘客模型返回结构化查询条件，车次、票价和余票由后端数据库查询生成。运营模型收到预定义报表口径及完整 SQL 候选，后端校验模板后绑定日期和车次执行。异常状态由程序规则判定，模型基于汇总与采样生成解释，解释中的原因推测需人工验证。

本记录中的退款订单、空候补结果和缓冲样本反映采集时的演示库。checked_at 保留原始UTC格式，展示时可换算为北京时间。所有提示词、工具定义、模型 JSON 和后端结果均完整保留，模拟样本在对应案例中明确标记。
