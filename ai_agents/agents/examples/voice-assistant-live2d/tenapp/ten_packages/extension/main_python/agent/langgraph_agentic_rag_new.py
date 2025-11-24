import os
from typing import Annotated, Sequence, TypedDict
from typing import Literal

from langchain_community.embeddings import ZhipuAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import create_retriever_tool
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition
from pydantic import BaseModel, Field

from .RAGFlowRetriever import create_ragflow_retriever




# 获取当前 Python 文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
chroma_db_dir = os.path.join(current_dir, 'chroma_db')

print('✅ 发现已存在的 Chroma 数据库，正在加载...')
# 加载已有的 Chroma 向量数据库
embeddings = ZhipuAIEmbeddings(
    model="embedding-2",
    api_key="569d1fc0e3734ddea956bb63fe9fef75.ASLL7ikeolDpsZkT"
)
vectorstore = Chroma(
    collection_name="rag_local_markdown_docs",
    embedding_function=embeddings,
    persist_directory="./chroma_db"
)
retriever_livermore = vectorstore.as_retriever()
print('✅ 已有向量数据库加载成功！')

# 关于 Jesse Livermore 的检索工具
retriever_livermore_tool = create_retriever_tool(
    retriever_livermore,
    # 工具名称
    name="retriever_livermore_biography",
    # 工具描述 作用: 告诉代理何时以及如何使用此工具
    description="""搜索并返回关于杰西·利弗莫尔(Jesse Livermore)传记的相关信息。
    使用此工具来回答关于以下方面的问题：
    - 利弗莫尔的生平经历和重要事件
    - 他的交易策略和投资哲学
    - 股市传奇故事和历史背景
    - 与巴菲特、格雷厄姆等投资大师的比较
    - 美股历史和交易技巧相关内容
    当用户询问利弗莫尔的个人信息、交易经历、投资理念或相关金融历史时使用此工具。"""
)

# 关于制造工程体验课程的检索工具
ragflow_retriever = create_ragflow_retriever()

ragflow_retriever_tool = create_retriever_tool(
    ragflow_retriever,
    # 工具名称
    name="retrieve_Manufacturing_Engineering_Experience_Course",
    # 工具描述 作用: 告诉代理何时以及如何使用此工具
    description="""搜索并返回关于制造工程体验课程的相关信息。
    使用此工具来回答关于以下方面的问题：
    - 制造工程体验课程的主讲人和内容
    - 制造工程体验课程的介绍
    - 制造工程体验课课程内容
    当用户询问关于制造工程体验课程相关问题时使用此工具。"""
)

tools = [ragflow_retriever_tool, retriever_livermore_tool]

## Agent State
# RAG 简洁版中文 Prompt
prompt = ChatPromptTemplate.from_template(
    """你是一个专业的问答助手。请根据以下检索到的上下文内容来回答问题。如果你不知道答案，请直接说不知道。请保持回答简洁，最多使用三句话。
问题：{question} 
上下文：{context} 
回答："""
)
print(f"简洁版中文 Prompt type: {type(prompt)}")
print(f"Input variables: {prompt.input_variables}")


# 图的状态类型定义
class AgentState(TypedDict):
    # The add_messages function defines how an update should be processed
    # Default is to replace. add_messages says "append"
    messages: Annotated[Sequence[BaseMessage], add_messages]


# 图的边的条件函数

def grade_documents(state) -> Literal["generate", "rewrite"]:
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (messages): The current state

    Returns:
        str: A decision for whether the documents are relevant or not
    """

    print("---CHECK RELEVANCE---")

    # Data model
    class grade(BaseModel):
        """Binary score for relevance check."""

        binary_score: str = Field(description="Relevance score 'yes' or 'no'")

    # LLM
    model = ChatDeepSeek(model="deepseek-chat", temperature=0, streaming=True)

    # LLM with tool and validation
    llm_with_tool = model.with_structured_output(grade)

    prompt = PromptTemplate(
        template="""你是一个文档相关性评估员，负责评估检索到的文档与用户问题的相关性。\n 
        以下是检索到的文档： \n\n {context} \n\n
        以下是用户问题： {question} \n
        如果文档包含与用户问题相关的关键词或语义内容，则评为相关。\n
        请给出二元评分 'yes' 或 'no' 来表示文档是否与问题相关。""",
        input_variables=["context", "question"],
    )

    # Chain
    chain = prompt | llm_with_tool

    messages = state["messages"]
    last_message = messages[-1]

    question = messages[0].content
    docs = last_message.content

    scored_result = chain.invoke({"question": question, "context": docs})

    score = scored_result.binary_score

    if score == "yes":
        print("---DECISION: DOCS RELEVANT---")
        return "generate"

    else:
        print("---DECISION: DOCS NOT RELEVANT---")
        print(score)
        return "rewrite"


### Nodes


def agent(state):
    """
    Invokes the agent model to generate a response based on the current state. Given
    the question, it will decide to retrieve using the retriever tool, or simply end.

    Args:
        state (messages): The current state

    Returns:
        dict: The updated state with the agent response appended to messages
    基于当前状态调用代理模型生成响应。根据问题，
    它将决定使用检索器工具进行检索，或直接结束。

    参数:
        state (messages): 当前状态

    返回:
        dict: 更新后的状态，其中代理响应已追加到消息中
    """
    print("---CALL AGENT---")
    messages = state["messages"]
    model = ChatDeepSeek(model="deepseek-chat", temperature=0, streaming=True)
    model = model.bind_tools(tools)
    response = model.invoke(messages)
    # We return a list, because this will get added to the existing list
    return {"messages": [response]}


def rewrite(state):
    """
    Transform the query to produce a better question.

    Args:
        state (messages): The current state

    Returns:
        dict: The updated state with re-phrased question
    """

    print("---TRANSFORM QUERY---")
    messages = state["messages"]
    question = messages[0].content

    msg = [
        HumanMessage(
            content=f""" \n 
    查看输入并尝试分析其底层的语义意图/含义。 \n 
    这是初始问题：
    \n ------- \n
    {question} 
    \n ------- \n
    请提出一个改进的问题： """,
        )
    ]

    # Grader
    # model = ChatOpenAI(temperature=0, model="gpt-4-0125-preview", streaming=True)
    model = ChatDeepSeek(model="deepseek-chat", temperature=0, streaming=True)
    response = model.invoke(msg)
    return {"messages": [response]}


def generate(state):
    """
    Generate answer

    Args:
        state (messages): The current state

    Returns:
         dict: The updated state with re-phrased question
    """
    print("---GENERATE---")
    messages = state["messages"]
    question = messages[0].content
    last_message = messages[-1]

    docs = last_message.content

    llm = ChatDeepSeek(model="deepseek-chat", temperature=0, streaming=True)

    # Post-processing
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    # Chain
    rag_chain = prompt | llm | StrOutputParser()

    # Run
    response = rag_chain.invoke({"context": docs, "question": question})
    return {"messages": [response]}


# 定义一个图对象
workflow = StateGraph(AgentState)

# Define the nodes we will cycle between
workflow.add_node("agent", agent)  # agent
retrieve = ToolNode(tools)
workflow.add_node("retrieve", retrieve)  # retrieval
workflow.add_node("rewrite", rewrite)  # Re-writing the question

# Call agent node to decide to retrieve or not
workflow.add_edge(START, "agent")

# Decide whether to retrieve
workflow.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "retrieve",  # 需要检索时调用工具
        END: END,  # 不需要检索时直接结束
    },
)

# Edges taken after the `retrieve` node is called.
workflow.add_conditional_edges(
    "retrieve",
    grade_documents,
    {
        "generate": END,  # 文档相关时直接结束，返回检索结果
        "rewrite": "rewrite"  # 文档不相关时重写查询
    }
)

# 重写后回到 agent 重新开始
workflow.add_edge("rewrite", "agent")

# Compile
graph = workflow.compile()

# import pprint
#
# os.environ['DEEPSEEK_API_KEY'] = 'sk-0511c57af3604877b63cf32ea9ae7f01'
# inputs = {
#     "messages": [
#         ("user", "利弗莫尔活了多少岁？"),
#     ]
# }
# inputs2 = {
#     "messages": [
#         ("user", "制造工程体验讲座是谁主讲的？"),
#     ]
# }
# for output in graph.stream(inputs):
#     for key, value in output.items():
#         pprint.pprint(f"Output from node '{key}':")
#         pprint.pprint("---")
#         pprint.pprint(value, indent=2, width=80, depth=None)
#     pprint.pprint("\n---\n")
#
# for output in graph.stream(inputs2):
#     for key, value in output.items():
#         pprint.pprint(f"Output from node '{key}':")
#         pprint.pprint("---")
#         pprint.pprint(value, indent=2, width=80, depth=None)
#     pprint.pprint("\n---\n")
