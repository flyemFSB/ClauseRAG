"""graph-topology 与 observability 辅助命令：打印 Agent 图结构与初始化监控存储。"""

from __future__ import annotations

import sys

import psycopg
from psycopg import sql

from agent_runtime.graph import build_agent_graph, recursion_limit
from composition.shared.retrieval import retrieval_budget
from infrastructure.config.settings import Settings, libpq_dsn, load_settings
from infrastructure.storage.s3_bucket import BucketInitializationError, S3BucketInitializer


def observability_init(settings: Settings) -> int:
    """初始化 Langfuse 专用的数据库与 S3 存储桶。"""
    try:
        with psycopg.connect(
            libpq_dsn(settings.database_url.get_secret_value()),
            autocommit=True,
        ) as connection:
            present = connection.execute(
                "select 1 from pg_database where datname = %s",
                (settings.langfuse_database,),
            ).fetchone()
            if present is None:
                # 数据库名使用标识符引用格式化
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.langfuse_database))
                )
                print(f"database {settings.langfuse_database} created")
            else:
                print(f"database {settings.langfuse_database} already present")
    except psycopg.Error as error:
        print(
            f"error: could not provision the Langfuse database: {type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    initializer = S3BucketInitializer(
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        bucket=settings.langfuse_bucket,
        timeout_seconds=settings.health_probe_timeout_seconds,
    )
    try:
        created = initializer.ensure_bucket()
    except BucketInitializationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    state = "created" if created else "already present"
    print(f"bucket {settings.langfuse_bucket} {state}")
    return 0


def graph_topology() -> int:
    """打印编译后的 Agent 执行图拓扑结构与预算配置。"""
    graph = build_agent_graph()
    drawn = graph.get_graph()
    budget = retrieval_budget(load_settings())
    print("nodes")
    for name in sorted(drawn.nodes):
        print(f"  {name}")
    print("edges")
    for edge in drawn.edges:
        marker = " (conditional)" if edge.conditional else ""
        print(f"  {edge.source} -> {edge.target}{marker}")
    print("bounds")
    print(f"  max_retrieval_rounds {budget.max_retrieval_rounds}")
    print(f"  recursion_limit {recursion_limit(budget.max_retrieval_rounds)}")
    return 0
