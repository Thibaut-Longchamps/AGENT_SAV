import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from orderops.access import DEMO_OPERATOR_ID
from orderops.agent.factory import build_agent
from orderops.config import get_settings
from orderops.evaluation import assess_case, load_evaluation_cases, observe_agent_run
from orderops.rag.store import build_vector_store


async def run_evaluations() -> bool:
    cases = load_evaluation_cases(Path("evals/cases.json"))
    settings = get_settings()
    rag_engine, vector_store = build_vector_store(settings)
    passed_count = 0

    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            agent, _mcp_client = await build_agent(settings, checkpointer, vector_store)
            for index, case in enumerate(cases, start=1):
                print(f"\n[{index}/{len(cases)}] {case.message}")
                try:
                    result = await agent.ainvoke(
                        {"messages": [{"role": "user", "content": case.message}]},
                        config={
                            "configurable": {
                                "thread_id": str(uuid4()),
                                "user_id": str(DEMO_OPERATOR_ID),
                                "approved": False,
                            }
                        },
                        version="v2",
                    )
                    observation = observe_agent_run(result.value, result.interrupts)
                    assessment = assess_case(case, observation)
                except Exception as exc:
                    print(f"  FAIL erreur d'exécution : {type(exc).__name__}: {exc}")
                    continue

                print(f"  tools appelés   : {list(observation.called_tools)}")
                print(f"  tools exécutés  : {list(observation.executed_tools)}")
                print(f"  approbation     : {observation.approval_requested}")
                if assessment.passed:
                    passed_count += 1
                    print("  PASS")
                else:
                    print("  FAIL " + " ; ".join(assessment.errors))
    finally:
        await rag_engine.dispose()

    print(f"\nRésultat : {passed_count}/{len(cases)} scénarios réussis")
    return passed_count == len(cases)


def main() -> None:
    sys.exit(0 if asyncio.run(run_evaluations()) else 1)


if __name__ == "__main__":
    main()
