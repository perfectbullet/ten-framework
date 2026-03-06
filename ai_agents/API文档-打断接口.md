# AI Agent 打断接口 API 文档

## 概述

打断接口允许外部系统主动触发 AI Agent 的中断功能，用于停止当前正在进行的 LLM 处理、TTS 播放，并刷新 RTC 流。

---

## 接口信息

### 基础信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Agent Interrupt |
| **请求方法** | `POST` |
| **请求路径** | `/interrupt` |
| **内容类型** | `application/json` |
| **响应格式** | `application/json` |

### 完整 URL

```
POST http://<server-host>:<port>/interrupt
```

**示例**：
- 本地开发：`http://localhost:8082/interrupt`
- 生产环境：`http://192.168.8.233:8082/interrupt`

---

## 请求参数

### Header

| Header | 值 | 必需 | 说明 |
|---------|-----|--------|------|
| `Content-Type` | `application/json` | 是 | 指定请求体为 JSON 格式 |

### Body 参数

| 参数名 | 类型 | 必需 | 说明 | 示例值 |
|--------|------|--------|------|---------|
| `request_id` | string | 否 | 请求唯一标识，用于追踪和日志 | `"550e8400-e29b-41d4-a716-446655440000"` |
| `channel_name` | string | 是 | Agent 的频道名称，对应启动 Agent 时指定的 channel | `"test_channel"` |

### 请求示例

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "channel_name": "test_channel"
}
```

---

## 响应格式

### 成功响应

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 状态码，`"0"` 表示成功 |
| `msg` | string | 响应消息 |
| `data` | null | 数据体，当前为 null |

**示例**：
```json
{
  "code": "0",
  "msg": "success",
  "data": null
}
```

### 错误响应

#### 1. 参数无效

| 字段 | 值 |
|------|-----|
| `code` | `"10000"` |
| `msg` | `"params invalid"` |

**示例**：
```json
{
  "code": "10000",
  "msg": "params invalid",
  "data": null
}
```

#### 2. 频道名称为空

| 字段 | 值 |
|------|-----|
| `code` | `"10001"` |
| `msg` | `"channel empty"` |

**示例**：
```json
{
  "code": "10001",
  "msg": "channel empty",
  "data": null
}
```

#### 3. 频道不存在

| 字段 | 值 |
|------|-----|
| `code` | `"10002"` |
| `msg` | `"channel not existed"` |

**示例**：
```json
{
  "code": "10002",
  "msg": "channel not existed",
  "data": null
}
```

#### 5. 文件操作失败

| 字段 | 值 |
|------|-----|
| `code` | `"10003"` |
| `msg` | `"read file failed"` / `"parse json failed"` / `"save file failed"` |

**示例**：
```json
{
  "code": "10003",
  "msg": "read file failed",
  "data": null
}
```

---

## 工作原理

### 中断流程

```
前端请求
    │
    ▼ POST /interrupt
    │
    ▼
API 服务器验证参数
    │
    ├─ channel 为空 → 返回错误 (10001)
    ├─ channel 不存在 → 返回错误 (10002)
    └─ 验证通过 ↓
    │
    ▼
修改 property.json
    在 ten.interrupt 下添加标记:
    {
      "ten": {
        "interrupt": {
          "action": "flush",
          "timestamp": 1709521234
        }
      }
    }
    │
    ▼
Agent 定期检查（每 1 秒）
    │
    ▼
检测到新的 interrupt 标记
    │
    ▼
执行打断操作:
    1. 刷新 LLM 输入队列
    2. 停止 TTS 播放
    3. 刷新 RTC 流
    │
    ▼
清除 interrupt 标记
    │
    ▼
返回成功响应 (code: "0")
```

### 响应时间

| 阶段 | 预计延迟 |
|------|----------|
| API 处理 | < 10ms |
| 文件读写 | < 50ms |
| Agent 检测 | 0-1000ms（最多 1 秒） |
| **总响应延迟** | **50-1050ms** |

---

## 使用示例

### 1. cURL 示例

```bash
curl -X POST 'http://localhost:8082/interrupt' \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id": "550e8400-e29b-41d4-a716-446655440001",
    "channel_name": "test_channel"
  }'
```

### 2. JavaScript / Fetch 示例

```javascript
async function interruptAgent(channelName) {
  const response = await fetch('http://localhost:8082/interrupt', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      request_id: crypto.randomUUID(),
      channel_name: channelName
    })
  });

  const result = await response.json();

  if (result.code === '0') {
    console.log('中断成功');
  } else {
    console.error('中断失败:', result.msg);
  }

  return result;
}

// 使用示例
interruptAgent('test_channel');
```

### 3. Python / requests 示例

```python
import requests
import uuid

def interrupt_agent(channel_name: str) -> dict:
    """触发 AI Agent 中断"""
    url = "http://localhost:8082/interrupt"
    headers = {"Content-Type": "application/json"}

    payload = {
        "request_id": str(uuid.uuid4()),
        "channel_name": channel_name
    }

    response = requests.post(url, json=payload, headers=headers)
    result = response.json()

    if result["code"] == "0":
        print("中断成功")
    else:
        print(f"中断失败: {result['msg']}")

    return result

# 使用示例
interrupt_agent("test_channel")
```

### 4. Axios 示例

```javascript
import axios from 'axios';

const interruptAgent = async (channelName) => {
  try {
    const response = await axios.post(
      'http://localhost:8082/interrupt',
      {
        request_id: crypto.randomUUID(),
        channel_name: channelName
      },
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    );

    if (response.data.code === '0') {
      console.log('中断成功');
    } else {
      console.error('中断失败:', response.data.msg);
    }

    return response.data;
  } catch (error) {
    console.error('请求失败:', error);
    throw error;
  }
};

// 使用示例
interruptAgent('test_channel');
```

---

## 前端集成建议

### 1. UI 交互

建议在以下场景提供中断按钮：

- **正在 AI 回复时**：显示"停止回复"按钮
- **正在语音播放时**：显示"停止播放"按钮
- **长对话轮次**：提供跳过当前轮次选项

### 2. 按钮状态管理

```javascript
// 示例：React 组件
function AgentControls({ channelId, isResponding }) {
  const [isInterrupting, setIsInterrupting] = useState(false);

  const handleInterrupt = async () => {
    if (isInterrupting) return;
    setIsInterrupting(true);

    try {
      await interruptAgent(channelId);
      // 延迟隐藏加载状态（Agent 检测需要最多 1 秒）
      setTimeout(() => setIsInterrupting(false), 1500);
    } catch (error) {
      setIsInterrupting(false);
      // 显示错误提示
      alert('中断失败，请重试');
    }
  };

  return (
    <button
      onClick={handleInterrupt}
      disabled={!isResponding || isInterrupting}
      className="interrupt-button"
    >
      {isInterrupting ? '正在停止...' : '⏹ 停止回复'}
    </button>
  );
}
```

### 3. 错误处理

```javascript
const handleInterrupt = async () => {
  try {
    const result = await interruptAgent(channelId);

    switch (result.code) {
      case '0':
        // 成功
        break;
      case '10001':
        alert('频道名称不能为空');
        break;
      case '10002':
        alert('指定的 Agent 不存在');
        break;
      default:
        alert(`操作失败: ${result.msg}`);
    }
  } catch (error) {
    // 网络错误或其他异常
    console.error('中断请求异常:', error);
    alert('网络连接失败，请检查服务器状态');
  }
};
```

---

## 注意事项

### 1. 前置条件

调用中断接口前，需要确保：

- ✅ Agent 已成功启动（通过 `/start` 接口）
- ✅ `channel_name` 参数与启动时使用的一致
- ✅ 网络连接正常

### 2. 频率限制

- ⚠️ 避免短时间内重复发送中断请求（建议间隔 > 2 秒）
- ⚠️ 中断操作是幂等的，多次发送相同时间戳的请求不会重复执行

### 3. 异步特性

- ⚠️ API 请求会立即返回（< 100ms），但实际中断操作需要额外时间
- ⚠️ Agent 检测延迟为 0-1000ms（平均 500ms）
- 💡 建议在 UI 中显示"正在停止..."状态

### 4. 并发处理

- ✅ 支持多个 Agent 并发中断（每个 channel 独立）
- ⚠️ 不会跨 channel 影响其他 Agent

---

## 相关接口

### 查看运行中的 Agents

```
GET /list
```

用于获取所有正在运行的 Agent，验证 `channel_name` 是否存在。

### 启动 Agent

```
POST /start
```

用于启动新的 Agent，获取可用的 `channel_name`。

---

## 附录

### 状态码完整列表

| Code | 消息 | 说明 |
|-------|--------|------|
| `"0"` | `success` | 操作成功 |
| `"10000"` | `params invalid` | 请求参数无效 |
| `"10001"` | `channel empty` | 频道名称为空 |
| `"10002"` | `channel not existed` | 指定的频道不存在 |
| `"10003"` | `read file failed` | 读取配置文件失败 |
| `"10004"` | `parse json failed` | JSON 解析失败 |
| `"10005"` | `save file failed` | 保存配置文件失败 |

### 端口配置

| 环境 | 默认端口 |
|------|---------|
| 开发环境 | `8082` |
| 生产环境 | 根据配置 |

### 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.0.0 | 2026-03-06 | 初始版本，实现基于 property.json 的中断机制 |

---

## 技术支持

如有问题，请联系技术支持或查看相关文档：
- TEN Framework 文档: https://theten.ai/docs
- GitHub Issues: https://github.com/TEN-framework/ten-framework/issues
