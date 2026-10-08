# Domain Glossary

## Knowledge Base
用户用于组织文档和检索范围的逻辑容器。一个知识库可以包含多个逻辑文档。

## Document
一份逻辑文档。文档更新不会改变其逻辑身份，而是产生新的 `DocumentVersion`。

## Document Version
一次具体上传和处理版本。原始对象、Markdown 产物、父子块与向量均必须关联版本。

## Ingestion Job
文档版本从上传到可检索的阶段化处理任务。任务状态是用户可见的业务事实，不以 RabbitMQ 消息作为事实来源。

## Parent Chunk
用于给 Agent 提供完整语义上下文的较大结构块。

## Child Chunk
实际参与向量/关键词召回和 rerank 的较小结构块。Child 必须关联 Parent。

## Retrieval Channel
一种独立召回方式。当前包括 dense、keyword。

## Evidence
经过召回、融合、rerank 并通过证据门控的候选内容。召回结果不自动等于证据。

## Citation
答案中指向本次检索上下文的短 ID。模型选择 Citation ID，后端验证并解析原文。

## Agent Run
一次 LangGraph Agent 执行。其运行状态由 checkpoint 保存；业务文档、任务和引用不由 checkpoint 代替。
