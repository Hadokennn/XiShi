import asyncio
import json
from openai import AsyncOpenAI
from xishi.config import settings

async def main() -> None:
    async with AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
    ) as client:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=256,
            messages=[{"role": "user", "content": "用一句话介绍夕拾这个项目"}],
        )
        # print(response.choices[0].message.content)
        print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())

# {
#   "id": "d53fbed8-d2d9-4357-b8e8-86d336be8c98",
#   "choices": [
#     {
#       "finish_reason": "stop",
#       "index": 0,
#       "logprobs": null,
#       "message": {
#         "content": "夕拾是一个专注于系统性整理个人数字记忆与碎片化信息，帮助用户对抗遗忘、沉淀知识并构建自定义知识库的工具。",
#         "refusal": null,
#         "role": "assistant",
#         "annotations": null,
#         "audio": null,
#         "function_call": null,
#         "tool_calls": null
#       }
#     }
#   ],
#   "created": 1778569465,
#   "model": "deepseek-v4-flash",
#   "object": "chat.completion",
#   "service_tier": null,
#   "system_fingerprint": "fp_8b330d02d0_prod0820_fp8_kvcache_20260402",
#   "usage": {
#     "completion_tokens": 28,
#     "prompt_tokens": 11,
#     "total_tokens": 39,
#     "completion_tokens_details": null,
#     "prompt_tokens_details": {
#       "audio_tokens": null,
#       "cached_tokens": 0
#     },
#     "prompt_cache_hit_tokens": 0,
#     "prompt_cache_miss_tokens": 11
#   }
# }