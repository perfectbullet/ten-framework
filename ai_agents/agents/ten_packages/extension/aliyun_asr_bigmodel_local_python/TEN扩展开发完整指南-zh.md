# TEN 扩展开发完整指南（/docs/ten_framework/development/how_to_develop_with_ext）

TEN 框架提供丰富的扩展模板，帮助开发者快速创建扩展并完成从开发到测试的全流程。本指南将通过实际操作，详细演示如何使用 C++、Go、Python 和 Node.js 进行完整的扩展开发工作流。

## 开发前准备

### 环境要求

开始扩展开发前，请确保开发环境已正确配置。通过以下命令验证安装：

```bash
tman --version
```

正常情况下，你应看到类似如下的版本信息输出：

```bash
TEN Framework version: <version>
```

> **重要说明**：请确保使用的 `tman` 版本 ≥ 0.10.12。如果版本过低，请前往 [GitHub Releases](https://github.com/TEN-framework/ten-framework/releases) 下载最新版本。

### 开发工作流概述

无论使用哪种编程语言，TEN 扩展开发均遵循以下标准化工作流：

1. **项目创建** - 使用官方模板生成扩展项目骨架
2. **依赖安装** - 配置运行环境并安装必要的依赖包
3. **核心开发** - 实现扩展业务逻辑与功能代码
4. **构建与测试** - 编译项目（如需）并执行单元测试
5. **调试与优化** - 使用专业调试工具定位并解决问题

***

## Python 扩展开发

Python 扩展具有最高的开发效率，特别适用于快速原型开发、AI/ML 应用集成、复杂业务逻辑实现等场景。

### 创建项目

使用 Python 异步扩展模板创建项目：

```bash
tman create extension my_example_ext_python --template default_async_extension_python --template-data class_name_prefix=Example
```

完整项目结构：

```bash
my_example_ext_python/
├── extension.py         # 扩展核心实现代码
├── addon.py             # 扩展插件注册入口
├── __init__.py          # Python 包初始化文件
├── requirements.txt     # Python 依赖包列表
├── manifest.json        # 扩展元数据配置
├── property.json        # 扩展属性配置
├── tests/               # 测试相关文件
│   ├── test_basic.py    # 基础测试用例
│   ├── conftest.py      # pytest 配置文件
│   └── bin/start        # 测试启动脚本
└── .vscode/launch.json  # VSCode 调试配置
```

### 依赖包安装

安装项目所需的 Python 依赖包：

```bash
tman install --standalone
```

### 运行测试

验证 Python 扩展功能：

#### 方法 1：使用启动脚本

```bash
./tests/bin/start
```

#### 方法 2：使用 tman 命令

```bash
tman run test
```

测试执行成功的示例输出：

```bash
============================================ test session starts ============================================
platform linux -- Python 3.10.17, pytest-8.3.4, pluggy-1.5.0
tests/test_basic.py .                                                                                [100%]
============================================ 1 passed in 0.04s =======================================
```

### 核心代码结构说明

#### 扩展实现（extension.py）

Python 扩展推荐使用现代异步编程模式，以获得更好的性能和并发处理能力：

```python
from ten_runtime import (
    AudioFrame, VideoFrame, AsyncExtension, AsyncTenEnv,
    Cmd, StatusCode, CmdResult, Data
)

class ExampleExtension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_init")

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_start")
        # TODO: 在此处读取配置文件，初始化必要资源

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug(f"on_cmd name {cmd_name}")

        # TODO: 在此处实现具体业务逻辑处理
        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_stop")
        # TODO: 在此处清理资源，执行优雅关闭
```

#### 插件注册入口（addon.py）

扩展插件的注册与创建逻辑：

```python
from ten_runtime import Addon, register_addon_as_extension, TenEnv
from .extension import ExampleExtension

@register_addon_as_extension("my_example_ext_python")
class ExampleExtensionAddon(Addon):
    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        ten_env.log_info("on_create_instance")
        ten_env.on_create_instance_done(ExampleExtension(name), context)
```

#### 测试实现（tests/test_basic.py）

完整的异步测试框架实现：

```python
from ten_runtime import (
    AsyncExtensionTester, AsyncTenEnvTester, Cmd, StatusCode,
    TenError, TenErrorCode
)

class ExtensionTesterBasic(AsyncExtensionTester):
    async def on_start(self, ten_env: AsyncTenEnvTester) -> None:
        # 创建测试用命令对象
        new_cmd = Cmd.create("hello_world")

        ten_env.log_debug("send hello_world")
        result, err = await ten_env.send_cmd(new_cmd)

        # 验证测试结果正确性
        if (err is not None or result is None
            or result.get_status_code() != StatusCode.OK):
            ten_env.stop_test(TenError.create(
                TenErrorCode.ErrorCodeGeneric,
                "Failed to send hello_world"
            ))
        else:
            ten_env.stop_test()

def test_basic():
    tester = ExtensionTesterBasic()
    tester.set_test_mode_single("my_example_ext_python")
    err = tester.run()
    if err is not None:
        assert False, err.error_message()
```

### 调试环境配置

#### VSCode 集成调试

确保已安装 Python 扩展和 debugpy 调试器，使用以下配置进行调试：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "独立测试（debugpy，启动）",
      "type": "debugpy",
      "request": "launch",
      "python": "/usr/bin/python3",
      "module": "pytest",
      "args": ["-s", "${workspaceFolder}/tests/test_basic.py"],
      "env": {
        "TEN_ENABLE_PYTHON_DEBUG": "true",
        "PYTHONPATH": "${workspaceFolder}/.ten/app/ten_packages/system/ten_runtime_python/lib:${workspaceFolder}/.ten/app/ten_packages/system/ten_runtime_python/interface:${workspaceFolder}"
      },
      "console": "integratedTerminal"
    }
  ]
}
```

***


## 开发总结

遵循本指南提供的完整开发流程，你可以高效地进行 TEN 扩展的开发、测试和调试。无论选择 C++、Go、Python 还是 Node.js，TEN 框架都为你提供了完整的工具链和最佳实践，帮助你充分发挥 TEN 框架的强大功能，构建高性能、高可靠性的扩展应用。

每种语言都有其独特的优势和适用场景：

* **C++**：适用于对性能要求极高的场景，如实时音视频处理、高频计算
* **Go**：在高性能和开发效率之间取得平衡，适用于网络服务、并发处理
* **Python**：具有最高的开发效率，特别适用于 AI/ML 应用、快速原型开发
* **Node.js**：提供现代化的 Web 开发体验，适用于前端技术栈扩展、实时应用

请根据你的具体需求和团队技术栈选择最合适的开发方案。开发过程中，建议充分利用 TEN 框架提供的调试工具和测试框架，确保扩展的质量和稳定性。
