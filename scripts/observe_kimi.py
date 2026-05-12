import asyncio
import json
from openai import AsyncOpenAI
from xishi.config import settings

async def main() -> None:
    async with AsyncOpenAI(
        api_key=settings.moonshot_api_key,
        base_url="https://api.moonshot.cn/v1",
    ) as client:
        response = await client.chat.completions.create(
            model="kimi-k2-0905-preview",
            messages=[{"role": "user", "content": "用一句话介绍夕拾这个项目"}],
        )
        # print(response.choices[0].message.content)
        print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())

# {
#   "id": "chatcmpl-6a029b132af1bf47c160fa68",
#   "choices": [
#     {
#       "finish_reason": "stop",
#       "index": 0,
#       "logprobs": null,
#       "message": {
#         "content": "夕拾是一个用AI唤醒、整理与分享人生记忆的项目，让每个人的故事不再被遗忘。",
#         "refusal": null,
#         "role": "assistant",
#         "annotations": null,
#         "audio": null,
#         "function_call": null,
#         "tool_calls": null
#       }
#     }
#   ],
#   "created": 1778555668,
#   "model": "kimi-k2-0905-preview",
#   "object": "chat.completion",
#   "service_tier": null,
#   "system_fingerprint": null,
#   "usage": {
#     "completion_tokens": 21,
#     "prompt_tokens": 13,
#     "total_tokens": 34,
#     "completion_tokens_details": null,
#     "prompt_tokens_details": null
#   }
# }