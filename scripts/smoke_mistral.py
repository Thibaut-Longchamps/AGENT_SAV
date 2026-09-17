import asyncio

from langchain_mistralai import ChatMistralAI

from orderops.config import get_settings


async def main() -> None:
    settings = get_settings()
    model = ChatMistralAI(
        model=settings.mistral_chat_model,
        api_key=settings.mistral_api_key.get_secret_value(),
        temperature=0,
        timeout=60,
        max_retries=2,
    )
    response = await model.ainvoke([{"role": "user", "content": "Réponds uniquement : Mistral OK"}])
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
