import os

from funasr import AutoModel
import soundfile

# 获取脚本所在目录
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认模型目录：脚本同级目录下的 speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx
DEFAULT_MODEL_DIR = os.path.join(
    _SCRIPT_DIR,
    "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx",
)


chunk_size = 200  # ms

fsmn_vad_model_path = ""
model = AutoModel(model="fsmn-vad", device="cpu", disable_update=True)

print(model)
print(model.model_path)
# 遍历模型参数，看 device
for name, param in model.model.named_parameters():
    print(f"{name}: {param.device}")
    break  # 看一个就够

wav_file = f"{model.model_path}/example/vad_example.wav"

speech, sample_rate = soundfile.read(wav_file)
chunk_stride = int(chunk_size * sample_rate / 1000)

cache = {}
total_chunk_num = int(len((speech) - 1) / chunk_stride + 1)
for i in range(total_chunk_num):
    speech_chunk = speech[i * chunk_stride : (i + 1) * chunk_stride]
    is_final = i == total_chunk_num - 1
    res = model.generate(
        input=speech_chunk, cache=cache, is_final=is_final, chunk_size=chunk_size
    )
    if len(res[0]["value"]):
        print(res)
