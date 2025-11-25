from vllm import LLM, SamplingParams
from transformers import AutoTokenizer
from pydantic import BaseModel
from typing import List, Any, Optional
import time
import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 配置日志
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{log_dir}/turn_detection.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# The Hugging Face ID for the Turn Detection model
MODEL_ID = os.getenv("MODEL_ID", "TEN-framework/TEN_Turn_Detection")
GPU_MEMORY_UTILIZATION = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.9"))

# --- FastAPI App ---
app = FastAPI(
    title="TEN Turn Detection API",
    description="OpenAI-compatible Turn Detection endpoint",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Model Initialization (Runs once at startup) ---
tokenizer = None
llm = None


@app.on_event("startup")
async def startup_event():
    """在应用启动时初始化模型"""
    global tokenizer, llm
    
    logger.info(f"Loading model: {MODEL_ID}")
    
    try:
        # Initialize the tokenizer for chat template formatting
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
        logger.info("Tokenizer loaded successfully")
        
        # Initialize the vLLM model globally
        llm = LLM(
            model=MODEL_ID,
            trust_remote_code=True,
            dtype="auto",
            gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
        )
        logger.info("Model loaded successfully")
        
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


# --- Pydantic Models for OpenAI Compatibility ---

class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: List[Message]
    model: str = MODEL_ID
    temperature: float = 0.1
    top_p: float = 0.1
    max_tokens: int = 1
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[Any]
    usage: Optional[dict] = None


# --- Endpoints ---

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "model": MODEL_ID,
        "model_loaded": llm is not None
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible Turn Detection endpoint.
    Works directly with OpenAI Python client.
    """
    
    if llm is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Extract system prompt and user content
        system_prompt = ""
        user_content = ""
        
        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "user":
                user_content = msg.content
        
        if not user_content:
            raise HTTPException(
                status_code=400,
                detail="At least one user message is required"
            )
        
        # Format using chat template
        formatted_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        
        formatted_prompt = tokenizer.apply_chat_template(
            formatted_messages, add_generation_prompt=True, tokenize=False
        )
        
        # Configure sampling for single-token classification
        sampling_params = SamplingParams(
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=1,  # Single token: finished/unfinished/wait
        )
        
        # Generate output
        outputs = llm.generate([formatted_prompt], sampling_params)
        turn_state = outputs[0].outputs[0].text.strip()
        
        # Build OpenAI-compatible response
        response = ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            object="chat.completion",
            created=int(time.time()),
            model=request.model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": turn_state},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": len(user_content.split()),
                "completion_tokens": 1,
                "total_tokens": len(user_content.split()) + 1,
            },
        )
        
        logger.info(f"Turn detection result: {turn_state}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 保留原有的 run 函数以兼容 Cerebrium
def run(
    messages: list,
    model: str = MODEL_ID,
    run_id: str = None,
    temperature: float = 0.1,
    top_p: float = 0.1,
    max_tokens: int = 1,
    stream: bool = False,
    **kwargs,
) -> dict:
    """兼容 Cerebrium 的原有接口"""
    
    request = ChatCompletionRequest(
        messages=[Message(**msg) for msg in messages],
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stream=stream
    )
    
    response = chat_completions(request)
    return response.model_dump()