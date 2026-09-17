import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from orderops.access import DEMO_OPERATOR_ID
from orderops.agent.factory import build_agent
from orderops.config import get_settings
from orderops.rag.store import build_vector_store
from orderops.repositories.conversations import ConversationStore


async def main() -> None:
    settings = get_settings()
    rag_engine, vector_store = build_vector_store(settings)
    store = ConversationStore()
    user = await store.get_user(DEMO_OPERATOR_ID)
    if user is None:
        raise RuntimeError("Appliquez les migrations pour créer les profils de démonstration.")
    conversation = await store.create(user, "Smoke test — retard CMD-1042")
    config = {
        "configurable": {
            "thread_id": str(conversation.thread_id),
            "user_id": str(user.user_id),
            "approved": False,
        }
    }
    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            agent, _client = await build_agent(settings, checkpointer, vector_store)
            result = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "La commande CMD-1042 est en retard. Vérifie-la et propose "
                                "un incident si la procédure l'exige."
                            ),
                        }
                    ]
                },
                config=config,
                version="v2",
            )
            print("Interruptions :", result.interrupts)
            await store.save_state(
                conversation.thread_id, actions=[interrupt.value for interrupt in result.interrupts]
            )
            if result.interrupts:
                print("Ouvrez ce chat dans Streamlit avec le profil Superviseur pour décider.")
    finally:
        await rag_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
