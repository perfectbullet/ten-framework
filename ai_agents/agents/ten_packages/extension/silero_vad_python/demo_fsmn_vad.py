import os

from funasr import AutoModel
import soundfile

# 获取脚本所在目录
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认模型目录：脚本同级目录下的 speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx
DEFAULT_MODEL_DIR = os.path.join(
    _SCRIPT_DIR,
    "speech_fsmn_vad_zh-cn-16k-common-pytorch",
)


chunk_size = 200  # ms

fsmn_vad_model_path = ""
model = AutoModel(model=DEFAULT_MODEL_DIR, device="cpu", disable_update=True)

print(model.model_path)
# 遍历模型参数，看 device

wav_file = f"{model.model_path}/example/vad_example.wav"

speech, sample_rate = soundfile.read(wav_file)
chunk_stride = int(chunk_size * sample_rate / 1000)

cache = {}
total_chunk_num = int(len((speech) - 1) / chunk_stride + 1)
for i in range(total_chunk_num):
    speech_chunk = speech[i * chunk_stride : (i + 1) * chunk_stride]
    is_final = i == total_chunk_num - 1

    # 注：流式 VAD 模型输出格式为 4 种情况：
    # [[beg1, end1], [beg2, end2], .., [begN, endN]]：同上离线 VAD 输出结果。
    # [[beg, -1]]：表示只检测到起始点。
    # [[-1, end]]：表示只检测到结束点。
    # []：表示既没有检测到起始点，也没有检测到结束点 输出结果单位为毫秒，从起始点开始的绝对时间。
    res = model.generate(
        input=speech_chunk, cache=cache, is_final=is_final, chunk_size=chunk_size
    )
    if len(res[0]["value"]):
        print(res)
