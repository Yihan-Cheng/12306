# 乘客端与管理端 AI 演示完整回答

采集时间为 2026-11-24T19:01:32+08:00。以下逐例保存同一次实测的模型原始响应和应用完整返回，共 21 个用例。

乘客 P1 至 P7 使用真实 DeepSeek。管理端的合成回复、故障注入和样本检测均在对应条目标明。凡有 SQL 的用例，查询均按记录所示在本机执行。

[演示摘要与现场顺序](AI演示实测报告.md) · [完整请求及 SQL、Cypher 的执行结果](AI演示实测记录.json)

## 目录

- [乘客端](#乘客端)（P1–P8）
- [运营问答](#运营问答)（O1–O7）
- [异常检测](#异常检测)（A1–A3）
- [AI 订票员](#AI-订票员)（B1–B3）

## 乘客端

### P1 正常

> 两个人从南通西到上海虹桥，下午三点前到，只看二等座和直达，选最便宜的。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "两个人从南通西到上海虹桥，下午三点前到，只看二等座和直达，选最便宜的。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南通西",
  "destination": "上海虹桥",
  "date": "2026-10-14",
  "people": 2,
  "arrive_by": "15:00",
  "seat": "二等座",
  "transfer": "direct",
  "sort": "price",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

完整模型响应

```json
{
  "id": "chatcmpl-aca0b65c-0405-9cd5-b6ed-cd6a20b0f826",
  "object": "chat.completion",
  "created": 1795518073,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_6e962e56b1b0405fb4f4ea03",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南通西\", \"destination\": \"上海虹桥\", \"date\": \"2026-10-14\", \"people\": 2, \"arrive_by\": \"15:00\", \"seat\": \"二等座\", \"transfer\": \"direct\", \"sort\": \"price\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"\"}"
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
    "prompt_tokens": 967,
    "total_tokens": 1261,
    "completion_tokens": 294,
    "prompt_tokens_details": {
      "cached_tokens": 768,
      "image_tokens": 0,
      "text_tokens": 967
    },
    "completion_tokens_details": {
      "text_tokens": 294
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "summary": "2026-10-14 · 南通西 → 上海虹桥 · 2 人 · 仅直达 · 二等座 · 15:00 前到",
  "people": 2,
  "date": "2026-10-14",
  "checked_at": "2026-11-24 19:01:22",
  "answer": "直达方案满足所选条件。",
  "ranking": "各类方案按票价排序",
  "options": [
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
          "available_seats": "268"
        }
      ],
      "price": "79.00",
      "group_price": "158.00",
      "transfer_minutes": 0,
      "duration_minutes": 77
    },
    {
      "legs": [
        {
          "train_no": "D5458",
          "from_station_name": "南通西",
          "to_station_name": "上海虹桥",
          "from_station_id": 1007,
          "to_station_id": 1003,
          "run_id": 227,
          "departure_at": "2026-10-14 09:36:00",
          "arrival_at": "2026-10-14 10:56:00",
          "seat_type_id": 3,
          "seat_type_name": "二等座",
          "amount": "79.00",
          "available_seats": "270"
        }
      ],
      "price": "79.00",
      "group_price": "158.00",
      "transfer_minutes": 0,
      "duration_minutes": 80
    },
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
      "transfer_minutes": 0,
      "duration_minutes": 77
    }
  ]
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P2 正常

> 两个人从南通西到上海虹桥，下午三点前到，可以换乘一次，想同时看看直达和换乘。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "两个人从南通西到上海虹桥，下午三点前到，可以换乘一次，想同时看看直达和换乘。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南通西",
  "destination": "上海虹桥",
  "date": "2026-10-14",
  "people": 2,
  "arrive_by": "15:00",
  "seat": "",
  "transfer": "allowed",
  "sort": "arrival",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

完整模型响应

```json
{
  "id": "chatcmpl-8f35eb7e-900e-9469-b265-f6467e5e4ce4",
  "object": "chat.completion",
  "created": 1795518073,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_f7651ff3c01242a19c2b62fb",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南通西\", \"destination\": \"上海虹桥\", \"date\": \"2026-10-14\", \"people\": 2, \"arrive_by\": \"15:00\", \"seat\": \"\", \"transfer\": \"allowed\", \"sort\": \"arrival\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"\"}"
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
    "prompt_tokens": 970,
    "total_tokens": 1262,
    "completion_tokens": 292,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 970
    },
    "completion_tokens_details": {
      "text_tokens": 292
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "summary": "2026-10-14 · 南通西 → 上海虹桥 · 2 人 · 最多换乘 1 次 · 15:00 前到",
  "people": 2,
  "date": "2026-10-14",
  "checked_at": "2026-11-24 19:01:22",
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
      "transfer_minutes": 0,
      "duration_minutes": 77
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
          "available_seats": "268"
        }
      ],
      "price": "79.00",
      "group_price": "158.00",
      "transfer_minutes": 0,
      "duration_minutes": 77
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
      "transfer_minutes": 0,
      "duration_minutes": 85
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
      "transfer_minutes": 22,
      "duration_minutes": 157
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
      "transfer_minutes": 15,
      "duration_minutes": 162
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
          "available_seats": 268,
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
          "available_seats": 178,
          "from_station_name": "嘉兴南",
          "to_station_name": "上海虹桥",
          "from_station_id": 1020,
          "to_station_id": 1003
        }
      ],
      "price": "153.50",
      "group_price": "307.00",
      "transfer_minutes": 21,
      "duration_minutes": 158
    }
  ]
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P3 边界

> 从南京南到杭州东，二等座，仅直达，人均预算最多 1 元。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "从南京南到杭州东，二等座，仅直达，人均预算最多 1 元。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南京南",
  "destination": "杭州东",
  "date": "2026-10-14",
  "people": 1,
  "arrive_by": "",
  "seat": "二等座",
  "transfer": "direct",
  "sort": "price",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "1",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

完整模型响应

```json
{
  "id": "chatcmpl-19b26b1f-a849-9cbf-8c20-3847e1804152",
  "object": "chat.completion",
  "created": 1795518074,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_10c73e13123b4c18ba07f2e4",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京南\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 1, \"arrive_by\": \"\", \"seat\": \"二等座\", \"transfer\": \"direct\", \"sort\": \"price\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"1\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"\"}"
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
    "prompt_tokens": 964,
    "total_tokens": 1254,
    "completion_tokens": 290,
    "prompt_tokens_details": {
      "cached_tokens": 768,
      "image_tokens": 0,
      "text_tokens": 964
    },
    "completion_tokens_details": {
      "text_tokens": 290
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "summary": "2026-10-14 · 南京南 → 杭州东 · 1 人 · 仅直达 · 二等座 · 人均不超过 ¥1",
  "people": 1,
  "date": "2026-10-14",
  "checked_at": "2026-11-24 19:01:23",
  "answer": "当前查询未找到满足这些条件的直达票。",
  "ranking": "各类方案按票价排序",
  "options": []
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P4 边界

> 6个人从南京南到杭州东，帮我买二等座。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "6个人从南京南到杭州东，帮我买二等座。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南京南",
  "destination": "杭州东",
  "date": "2026-10-14",
  "people": 6,
  "arrive_by": "",
  "seat": "二等座",
  "transfer": "direct",
  "sort": "arrival",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

完整模型响应

```json
{
  "id": "chatcmpl-29b2c63f-3bfc-9547-818c-78c3c705061e",
  "object": "chat.completion",
  "created": 1795518074,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_fe6da3e41c074609a0ba4a73",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京南\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 6, \"arrive_by\": \"\", \"seat\": \"二等座\", \"transfer\": \"direct\", \"sort\": \"arrival\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"\"}"
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
    "prompt_tokens": 957,
    "total_tokens": 1246,
    "completion_tokens": 289,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 957
    },
    "completion_tokens_details": {
      "text_tokens": 289
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "answer": "每次可查询 1 至 5 人，请修改人数。",
  "options": []
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P5 难回答

> 三个人从南京南去杭州东，只接受三连座，分开坐就不买。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "三个人从南京南去杭州东，只接受三连座，分开坐就不买。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南京南",
  "destination": "杭州东",
  "date": "2026-10-14",
  "people": 3,
  "arrive_by": "",
  "seat": "",
  "transfer": "direct",
  "sort": "arrival",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": "无法保证三人三连座（连座要求无法在查询中表达），请确认是否仍要继续查询？另外请补充出发日期或时间、席别等要求。"
}
```

完整模型响应

```json
{
  "id": "chatcmpl-bf42b27f-aa8e-97fd-a122-fce3fc091468",
  "object": "chat.completion",
  "created": 1795518082,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_77809587cb9645a3b31e92d2",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京南\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 3, \"arrive_by\": \"\", \"seat\": \"\", \"transfer\": \"direct\", \"sort\": \"arrival\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"无法保证三人三连座（连座要求无法在查询中表达），请确认是否仍要继续查询？另外请补充出发日期或时间、席别等要求。\"}"
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
    "prompt_tokens": 962,
    "total_tokens": 1284,
    "completion_tokens": 322,
    "prompt_tokens_details": {
      "cached_tokens": 0,
      "image_tokens": 0,
      "text_tokens": 962
    },
    "completion_tokens_details": {
      "text_tokens": 322
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "answer": "无法保证三人三连座（连座要求无法在查询中表达），请确认是否仍要继续查询？另外请补充出发日期或时间、席别等要求。",
  "options": []
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P6 难回答

> 我想下午三点前到杭州东，二等座。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "我想下午三点前到杭州东，二等座。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "",
  "destination": "杭州东",
  "date": "2026-10-14",
  "people": 1,
  "arrive_by": "15:00",
  "seat": "二等座",
  "transfer": "direct",
  "sort": "arrival",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": "请告诉我出发城市或车站（例如“上海虹桥”）。"
}
```

完整模型响应

```json
{
  "id": "chatcmpl-a1141c5c-42d0-97f2-96c8-a21ed18020ec",
  "object": "chat.completion",
  "created": 1795518082,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_7ccb71bb308d4e3c891a2abe",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 1, \"arrive_by\": \"15:00\", \"seat\": \"二等座\", \"transfer\": \"direct\", \"sort\": \"arrival\", \"depart_after\": \"\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"请告诉我出发城市或车站（例如“上海虹桥”）。\"}"
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
    "prompt_tokens": 954,
    "total_tokens": 1260,
    "completion_tokens": 306,
    "prompt_tokens_details": {
      "cached_tokens": 768,
      "image_tokens": 0,
      "text_tokens": 954
    },
    "completion_tokens_details": {
      "text_tokens": 306
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "answer": "请告诉我出发城市或车站（例如“上海虹桥”）。",
  "options": []
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P7 难回答

> 从南京南去杭州东，要晚上 18:00 后出发、同一天 15:00 前到。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "从南京南去杭州东，要晚上 18:00 后出发、同一天 15:00 前到。"
}
```

#### 模型回复

阿里云 DeepSeek 真实响应，工具 `plan_trip`，模型 HTTP 状态 `200`。

工具参数解码结果

```json
{
  "origin": "南京南",
  "destination": "杭州东",
  "date": "2026-10-14",
  "people": 1,
  "arrive_by": "15:00",
  "seat": "",
  "transfer": "direct",
  "sort": "arrival",
  "depart_after": "18:00",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

完整模型响应

```json
{
  "id": "chatcmpl-2c844c31-3cd3-95a2-837e-6e67b5d2a395",
  "object": "chat.completion",
  "created": 1795518083,
  "model": "deepseek-v4.1-flash-1017",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "",
        "tool_calls": [
          {
            "id": "call_119077c1da934182b3587597",
            "type": "function",
            "function": {
              "name": "plan_trip",
              "arguments": "{\"origin\": \"南京南\", \"destination\": \"杭州东\", \"date\": \"2026-10-14\", \"people\": 1, \"arrive_by\": \"15:00\", \"seat\": \"\", \"transfer\": \"direct\", \"sort\": \"arrival\", \"depart_after\": \"18:00\", \"depart_before\": \"\", \"max_fare\": \"\", \"max_group_fare\": \"\", \"train_no\": \"\", \"train_category\": \"\", \"max_duration_minutes\": \"\", \"clarify\": \"\"}"
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
    "prompt_tokens": 970,
    "total_tokens": 1265,
    "completion_tokens": 295,
    "prompt_tokens_details": {
      "cached_tokens": 768,
      "image_tokens": 0,
      "text_tokens": 970
    },
    "completion_tokens_details": {
      "text_tokens": 295
    }
  }
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 API",
  "answer": "最早出发时间须早于或等于最晚出发、到达时间。",
  "options": []
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### P8 故障注入

> 两个人从南通西到上海虹桥，二等座，15:00前到，不换乘。

接口 `POST /api/travel-assistant`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "两个人从南通西到上海虹桥，二等座，15:00前到，不换乘。"
}
```

#### 模型回复

注入超时，请求未发送，工具 `plan_trip`。

错误为 `injected TimeoutError before sending HTTP request`。

#### 应用接口完整响应

```json
{
  "mode": "本地规则（模型 API 暂不可用）",
  "summary": "2026-10-14 · 南通西 → 上海虹桥 · 2 人 · 仅直达 · 二等座 · 15:00 前到",
  "people": 2,
  "date": "2026-10-14",
  "checked_at": "2026-11-24 19:01:23",
  "answer": "直达方案满足所选条件。",
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
      "transfer_minutes": 0,
      "duration_minutes": 77
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
          "available_seats": "268"
        }
      ],
      "price": "79.00",
      "group_price": "158.00",
      "transfer_minutes": 0,
      "duration_minutes": 77
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
      "transfer_minutes": 0,
      "duration_minutes": 85
    }
  ]
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

## 运营问答

### O1 正常

> 订单状态分布

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "订单状态分布",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `query_operations`。

工具参数解码结果

```json
{
  "sql": "SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20",
  "clarify": ""
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\\nWHERE service_date = %s\\nGROUP BY order_status ORDER BY orders DESC, order_status\\nLIMIT 20\", \"clarify\": \"\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型 NL2SQL",
  "scope": "运营日 2026-10-14 · 全部车次",
  "title": "订单状态分布",
  "answer": "已支付 558 笔，待支付 156 笔，已退款 10 笔，已取消 3 笔。",
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
      "order_status": "PAID",
      "orders": 558
    },
    {
      "order_status": "PENDING_PAYMENT",
      "orders": 156
    },
    {
      "order_status": "REFUNDED",
      "orders": 10
    },
    {
      "order_status": "CANCELLED",
      "orders": 3
    }
  ],
  "sql": "SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20",
  "params": [
    "2026-10-14"
  ],
  "checked_at": "2026-11-24T11:01:24+00:00"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### O2 正常

> 2026-10-14 至 2026-10-16，按出发城市和客群统计订单数，区分 AI 订票员和其他乘客。

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "2026-10-14 至 2026-10-16，按出发城市和客群统计订单数，区分 AI 订票员和其他乘客。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_operations_query`。

工具参数解码结果

```json
{
  "metric": "order_count",
  "group_by": [
    "origin_city",
    "customer_kind"
  ],
  "filters": {},
  "sort": "desc",
  "limit": 20,
  "clarify": ""
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_operations_query",
              "arguments": "{\"metric\": \"order_count\", \"group_by\": [\"origin_city\", \"customer_kind\"], \"filters\": {}, \"sort\": \"desc\", \"limit\": 20, \"clarify\": \"\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型查询计划",
  "scope": "运营日 2026-10-14 至 2026-10-16 · 全部车次",
  "title": "订单数",
  "answer": "按出发城市、客群分组，共显示 20 组。结果超过 20 组，已按指标降序截取。",
  "definition": "匹配条件的票项按订单号去重。按席别、区间或车次分组时，同一笔订单可出现在多组。日期按列车运营日，状态按查询时当前值。",
  "columns": [
    [
      "origin_city",
      "出发城市"
    ],
    [
      "customer_kind",
      "客群"
    ],
    [
      "metric_value",
      "订单数（笔）"
    ]
  ],
  "rows": [
    {
      "origin_city": "杭州",
      "customer_kind": "SIMULATED",
      "metric_value": 94
    },
    {
      "origin_city": "上海",
      "customer_kind": "SIMULATED",
      "metric_value": 84
    },
    {
      "origin_city": "南京",
      "customer_kind": "SIMULATED",
      "metric_value": 72
    },
    {
      "origin_city": "合肥",
      "customer_kind": "SIMULATED",
      "metric_value": 49
    },
    {
      "origin_city": "苏州",
      "customer_kind": "SIMULATED",
      "metric_value": 49
    },
    {
      "origin_city": "常州",
      "customer_kind": "SIMULATED",
      "metric_value": 43
    },
    {
      "origin_city": "宁波",
      "customer_kind": "SIMULATED",
      "metric_value": 31
    },
    {
      "origin_city": "徐州",
      "customer_kind": "SIMULATED",
      "metric_value": 29
    },
    {
      "origin_city": "嘉兴",
      "customer_kind": "SIMULATED",
      "metric_value": 28
    },
    {
      "origin_city": "阜阳",
      "customer_kind": "SIMULATED",
      "metric_value": 26
    },
    {
      "origin_city": "温州",
      "customer_kind": "SIMULATED",
      "metric_value": 25
    },
    {
      "origin_city": "芜湖",
      "customer_kind": "SIMULATED",
      "metric_value": 25
    },
    {
      "origin_city": "蚌埠",
      "customer_kind": "SIMULATED",
      "metric_value": 24
    },
    {
      "origin_city": "淮南",
      "customer_kind": "SIMULATED",
      "metric_value": 21
    },
    {
      "origin_city": "金华",
      "customer_kind": "SIMULATED",
      "metric_value": 17
    },
    {
      "origin_city": "铜陵",
      "customer_kind": "SIMULATED",
      "metric_value": 17
    },
    {
      "origin_city": "丽水",
      "customer_kind": "SIMULATED",
      "metric_value": 15
    },
    {
      "origin_city": "衢州",
      "customer_kind": "SIMULATED",
      "metric_value": 15
    },
    {
      "origin_city": "盐城",
      "customer_kind": "SIMULATED",
      "metric_value": 12
    },
    {
      "origin_city": "黄山",
      "customer_kind": "SIMULATED",
      "metric_value": 12
    }
  ],
  "sql": "SELECT origin_city, customer_kind, COUNT(DISTINCT order_id) AS metric_value\nFROM v_ops_analysis_orders\nWHERE service_date BETWEEN %s AND %s\nGROUP BY origin_city, customer_kind\nORDER BY metric_value DESC, origin_city, customer_kind\nLIMIT 21",
  "params": [
    "2026-10-14",
    "2026-10-16"
  ],
  "empty_value": "—",
  "checked_at": "2026-11-24T11:01:24+00:00"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### O3 正常

> G8359 按车厢和席别统计全程空闲座位数。

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "G8359 按车厢和席别统计全程空闲座位数。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_operations_query`。

工具参数解码结果

```json
{
  "metric": "inventory_free",
  "group_by": [
    "carriage_no",
    "seat_type"
  ],
  "filters": {},
  "sort": "desc",
  "limit": 20,
  "clarify": ""
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_operations_query",
              "arguments": "{\"metric\": \"inventory_free\", \"group_by\": [\"carriage_no\", \"seat_type\"], \"filters\": {}, \"sort\": \"desc\", \"limit\": 20, \"clarify\": \"\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型查询计划",
  "scope": "运营日 2026-10-14 · G8359",
  "title": "全程空闲座位数",
  "answer": "按车厢、席别分组，共显示 4 组。",
  "definition": "占用位图为零的运行座位数。该指标衡量全程空闲，具体区间余票需单独查询。日期按列车运营日，状态按查询时当前值。",
  "columns": [
    [
      "carriage_no",
      "车厢"
    ],
    [
      "seat_type",
      "席别"
    ],
    [
      "metric_value",
      "全程空闲座位数（席）"
    ]
  ],
  "rows": [
    {
      "carriage_no": 4,
      "seat_type": "二等座",
      "metric_value": "90"
    },
    {
      "carriage_no": 3,
      "seat_type": "二等座",
      "metric_value": "77"
    },
    {
      "carriage_no": 2,
      "seat_type": "一等座",
      "metric_value": "27"
    },
    {
      "carriage_no": 1,
      "seat_type": "商务座",
      "metric_value": "7"
    }
  ],
  "sql": "SELECT carriage_no, seat_type, COALESCE(SUM(full_route_free), 0) AS metric_value\nFROM v_ops_analysis_inventory\nWHERE service_date IN (%s)\n  AND train_no IN (%s)\nGROUP BY carriage_no, seat_type\nORDER BY metric_value DESC, carriage_no, seat_type\nLIMIT 21",
  "params": [
    "2026-10-14",
    "G8359"
  ],
  "empty_value": "—",
  "checked_at": "2026-11-24T11:01:24+00:00"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### O4 难回答

> G3864 停哪些车站？

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "G3864 停哪些车站？",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_operations_query`。

工具参数解码结果

```json
{
  "metric": "",
  "group_by": [],
  "filters": {},
  "sort": "desc",
  "limit": 20,
  "clarify": "报表缺少经停站时刻表，可使用车次时刻表查询完整停站。"
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_operations_query",
              "arguments": "{\"metric\": \"\", \"group_by\": [], \"filters\": {}, \"sort\": \"desc\", \"limit\": 20, \"clarify\": \"报表缺少经停站时刻表，可使用车次时刻表查询完整停站。\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型查询计划",
  "clarify": "报表缺少经停站时刻表，可使用车次时刻表查询完整停站。"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### O5 难回答

> 把 G8359 所有乘客姓名和证件号按座位号列出来。

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "把 G8359 所有乘客姓名和证件号按座位号列出来。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_operations_query`。

工具参数解码结果

```json
{
  "metric": "",
  "group_by": [],
  "filters": {},
  "sort": "desc",
  "limit": 20,
  "clarify": "运营报表支持汇总，无法列出乘客姓名或证件号。"
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_operations_query",
              "arguments": "{\"metric\": \"\", \"group_by\": [], \"filters\": {}, \"sort\": \"desc\", \"limit\": 20, \"clarify\": \"运营报表支持汇总，无法列出乘客姓名或证件号。\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "模型查询计划",
  "clarify": "运营报表支持汇总，无法列出乘客姓名或证件号。"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### O6 边界

> 2026-10-01 至 2026-11-01，按运营日统计订单数。

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "2026-10-01 至 2026-11-01，按运营日统计订单数。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本用例未调用外部模型。

#### 应用接口完整响应

```json
{
  "mode": "模型查询计划",
  "clarify": "日期范围须按先后顺序填写，最多包含 31 天。"
}
```

### O7 故障注入

> 订单状态分布

接口 `POST /api/admin/operations/query`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "订单状态分布",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

注入不合规 SQL 的模拟回复，工具 `query_operations`。

工具参数解码结果

```json
{
  "sql": "SELECT 1",
  "clarify": ""
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "query_operations",
              "arguments": "{\"sql\": \"SELECT 1\", \"clarify\": \"\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "mode": "本地 NL2SQL 规则（模型 SQL 未通过校验）",
  "scope": "运营日 2026-10-14 · 全部车次",
  "title": "订单状态分布",
  "answer": "已支付 558 笔，待支付 156 笔，已退款 10 笔，已取消 3 笔。",
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
      "order_status": "PAID",
      "orders": 558
    },
    {
      "order_status": "PENDING_PAYMENT",
      "orders": 156
    },
    {
      "order_status": "REFUNDED",
      "orders": 10
    },
    {
      "order_status": "CANCELLED",
      "orders": 3
    }
  ],
  "sql": "SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders\nWHERE service_date = %s\nGROUP BY order_status ORDER BY orders DESC, order_status\nLIMIT 20",
  "params": [
    "2026-10-14"
  ],
  "checked_at": "2026-11-24T11:01:24+00:00"
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

## 异常检测

### A1 正常

> 运行检测

接口 `POST /api/admin/anomalies/check`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "date": "2026-10-14",
  "train": "G8359",
  "explain": false
}
```

#### 模型回复

本用例未调用外部模型。

#### 应用接口完整响应

```json
{
  "scope": "2026-10-14 · G8359 库存；全库订票缓冲",
  "checked_at": "2026-11-24T11:01:24+00:00",
  "inventory": {
    "status": "normal",
    "mask_mismatch_count": 0,
    "overlap_seat_count": 0,
    "checked_seats": 218,
    "anomaly_count": 0,
    "findings": [],
    "definition": "同一只读快照中，核对所选运营日与车次的全部现有运行座位。将 HOLD、CONFIRMED 分配区间的按位或与库存位图对比。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
  },
  "buffer": {
    "samples": [
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:12.868606"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:17.984041"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:23.108131"
      }
    ],
    "interval_seconds": 5,
    "window_seconds": 10,
    "definition": "全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。",
    "status": "normal",
    "message": "最近3次采样未触发持续积压规则。"
  }
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### A2 正常

> 检测并解释

接口 `POST /api/admin/anomalies/check`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "date": "2026-10-14",
  "train": "G8359",
  "explain": true
}
```

#### 模型回复

本机合成模型回复，工具 `explain_anomalies`。

工具参数解码结果

```json
{
  "explanation": "此段解读是本机测试用的合成文案。真实检测计数见结果。"
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "explain_anomalies",
              "arguments": "{\"explanation\": \"此段解读是本机测试用的合成文案。真实检测计数见结果。\"}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "scope": "2026-10-14 · G8359 库存；全库订票缓冲",
  "checked_at": "2026-11-24T11:01:24+00:00",
  "inventory": {
    "status": "normal",
    "mask_mismatch_count": 0,
    "overlap_seat_count": 0,
    "checked_seats": 218,
    "anomaly_count": 0,
    "findings": [],
    "definition": "同一只读快照中，核对所选运营日与车次的全部现有运行座位。将 HOLD、CONFIRMED 分配区间的按位或与库存位图对比。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
  },
  "buffer": {
    "samples": [
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:12.868606"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:17.984041"
      },
      {
        "queued": 0,
        "processing": 0,
        "oldest_seconds": 0,
        "expired_leases": 0,
        "retried": 0,
        "captured_at": "2026-11-24 19:01:23.108131"
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
    "model": "deepseek-v4.1-flash-1017",
    "text": "此段解读是本机测试用的合成文案。真实检测计数见结果。"
  }
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### A3 模拟样本

> 查看模拟异常

接口 `GET /api/admin/anomalies/demo`，HTTP 状态 `200`。

#### 模型回复

本用例未调用外部模型。

#### 应用接口完整响应

```json
{
  "source": "模拟证据样本，独立于业务数据",
  "scope": "模拟库存与模拟缓冲",
  "checked_at": "2026-11-24T11:01:24+00:00",
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
    "definition": "同一只读快照中，核对所选运营日与车次的全部现有运行座位。将 HOLD、CONFIRMED 分配区间的按位或与库存位图对比。另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"
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

## AI 订票员

### B1 正常

> 查 G8359 盐城到义乌二等座还有多少余票。

接口 `POST /api/admin/ai/preview`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "查 G8359 盐城到义乌二等座还有多少余票。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_ai_booking`。

工具参数解码结果

```json
{
  "intent": "availability",
  "train_no": "G8359",
  "origin": "盐城",
  "destination": "义乌",
  "seat_type": "二等座",
  "clarify": "",
  "users": null,
  "concurrency": null,
  "pay_rate": null,
  "reserve_seats": null,
  "waitlist": null
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_ai_booking",
              "arguments": "{\"intent\": \"availability\", \"train_no\": \"G8359\", \"origin\": \"盐城\", \"destination\": \"义乌\", \"seat_type\": \"二等座\", \"clarify\": \"\", \"users\": null, \"concurrency\": null, \"pay_rate\": null, \"reserve_seats\": null, \"waitlist\": null}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "target": {
    "run_id": 1799,
    "train_no": "G8359",
    "service_date": "2026-10-14",
    "origin": "盐城",
    "destination": "义乌",
    "from_order": 1,
    "to_order": 14,
    "seat_type_id": 3,
    "seat_type_name": "二等座",
    "available_seats": "167"
  },
  "task": null,
  "sql": "SELECT p.run_id, p.train_no, p.service_date, p.origin, p.destination,\n       p.from_order, p.to_order, p.seat_type_id, p.seat_type_name,\n       COALESCE((SELECT SUM((s.occupied_mask &\n           (((CAST(1 AS UNSIGNED) << (p.to_order - p.from_order)) - 1) << (p.from_order - 1))) = 0)\n           FROM v_ops_ai_seats s WHERE s.run_id = p.run_id AND s.seat_type_id = p.seat_type_id), 0)\n           AS available_seats\nFROM v_ops_ai_products p\nWHERE p.service_date = %s AND p.train_no = %s\n  AND p.origin = %s AND p.destination = %s AND p.seat_type_name = %s\nLIMIT 2",
  "params": [
    "2026-10-14",
    "G8359",
    "盐城",
    "义乌",
    "二等座"
  ]
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### B2 正常

> 给 G8359 盐城到义乌二等座预留 10 张，并发 2，全部支付，无票不候补，先预览。

接口 `POST /api/admin/ai/preview`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "给 G8359 盐城到义乌二等座预留 10 张，并发 2，全部支付，无票不候补，先预览。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_ai_booking`。

工具参数解码结果

```json
{
  "intent": "targeted",
  "train_no": "G8359",
  "origin": "盐城",
  "destination": "义乌",
  "seat_type": "二等座",
  "clarify": "",
  "users": null,
  "concurrency": 2,
  "pay_rate": 100,
  "reserve_seats": 10,
  "waitlist": false
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_ai_booking",
              "arguments": "{\"intent\": \"targeted\", \"train_no\": \"G8359\", \"origin\": \"盐城\", \"destination\": \"义乌\", \"seat_type\": \"二等座\", \"clarify\": \"\", \"users\": null, \"concurrency\": 2, \"pay_rate\": 100, \"reserve_seats\": 10, \"waitlist\": false}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "target": {
    "run_id": 1799,
    "train_no": "G8359",
    "service_date": "2026-10-14",
    "origin": "盐城",
    "destination": "义乌",
    "from_order": 1,
    "to_order": 14,
    "seat_type_id": 3,
    "seat_type_name": "二等座",
    "available_seats": "167"
  },
  "task": {
    "mode": "targeted",
    "users": 157,
    "concurrency": 2,
    "payRate": 100,
    "waitlist": false,
    "runId": 1799,
    "fromOrder": 1,
    "toOrder": 14,
    "seatTypeId": 3,
    "reserveSeats": 10
  },
  "sql": "SELECT p.run_id, p.train_no, p.service_date, p.origin, p.destination,\n       p.from_order, p.to_order, p.seat_type_id, p.seat_type_name,\n       COALESCE((SELECT SUM((s.occupied_mask &\n           (((CAST(1 AS UNSIGNED) << (p.to_order - p.from_order)) - 1) << (p.from_order - 1))) = 0)\n           FROM v_ops_ai_seats s WHERE s.run_id = p.run_id AND s.seat_type_id = p.seat_type_id), 0)\n           AS available_seats\nFROM v_ops_ai_products p\nWHERE p.service_date = %s AND p.train_no = %s\n  AND p.origin = %s AND p.destination = %s AND p.seat_type_name = %s\nLIMIT 2",
  "params": [
    "2026-10-14",
    "G8359",
    "盐城",
    "义乌",
    "二等座"
  ]
}
```

本用例执行的查询及原始行保存在 [JSON 记录](AI演示实测记录.json) 中对应编号的 `queries`。

### B3 边界

> 让 501 名乘客随机抢票，并发 4，先预览。

接口 `POST /api/admin/ai/preview`，HTTP 状态 `200`。

#### 应用请求

```json
{
  "question": "让 501 名乘客随机抢票，并发 4，先预览。",
  "serviceDate": "2026-10-14"
}
```

#### 模型回复

本机合成模型回复，工具 `plan_ai_booking`。

工具参数解码结果

```json
{
  "intent": "random",
  "train_no": "",
  "origin": "",
  "destination": "",
  "seat_type": "",
  "clarify": "",
  "users": 501,
  "concurrency": null,
  "pay_rate": null,
  "reserve_seats": null,
  "waitlist": null
}
```

完整模型响应

```json
{
  "choices": [
    {
      "message": {
        "tool_calls": [
          {
            "function": {
              "name": "plan_ai_booking",
              "arguments": "{\"intent\": \"random\", \"train_no\": \"\", \"origin\": \"\", \"destination\": \"\", \"seat_type\": \"\", \"clarify\": \"\", \"users\": 501, \"concurrency\": null, \"pay_rate\": null, \"reserve_seats\": null, \"waitlist\": null}"
            }
          }
        ]
      }
    }
  ]
}
```

#### 应用接口完整响应

```json
{
  "clarify": "参数超出范围。人数 1–500，并发 1–30，支付率 0–100%，预留 0–500 张。"
}
```

