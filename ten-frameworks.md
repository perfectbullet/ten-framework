# ten-frameworks

TEN 包含[TEN 框架](https://github.com/ten-framework/ten-framework)、[TEN 转弯检测](https://github.com/ten-framework/ten-turn-detection)、[TEN VAD](https://github.com/ten-framework/ten-vad)、[TEN 代理](https://github.com/TEN-framework/ten-framework/tree/main/ai_agents/demo)、[TMAN 设计器](https://github.com/TEN-framework/ten-framework/tree/main/core/src/ten_manager/designer_frontend)和[TEN 门户](https://github.com/ten-framework/portal)。查看[🌍 TEN 生态系统](https://github.com/TEN-framework/ten-framework?tab=readme-ov-file#-ten-ecosystem)了解更多详情。

TEN 包含 [TEN Framework](https://github.com/ten-framework/ten-framework), [TEN Turn Detection](https://github.com/ten-framework/ten-turn-detection), [TEN VAD](https://github.com/ten-framework/ten-vad), [TEN Agent](https://github.com/TEN-framework/ten-framework/tree/main/ai_agents/demo), [TMAN Designer](https://github.com/TEN-framework/ten-framework/tree/main/core/src/ten_manager/designer_frontend), and [TEN Portal](https://github.com/ten-framework/portal). Check out [🌍 TEN Ecosystem](https://github.com/TEN-framework/ten-framework?tab=readme-ov-file#-ten-ecosystem) for more details.



```
AGORA_APP_ID=
AGORA_APP_CERTIFICATE=
```



## 布道师得碎碎念

 TEN 的布道师，我叫 Elliot - 陈亦凡 （人送外号，彦祖）

TEN 是一个开源的平台型框架，专注于创建实时多模态的对话式 AI

TEN 开源的项目有

• 核心框架本身 - TEN Framework 

• 高性能打断器 - TEN VAD 

• 中英语义检测器 - TEN Turn Detection

• 实时多模态对话 Agent - TEN Agent

• 可视化编辑器 - Designer

• 官方网站和文档 - Portal

开源不易，国际礼仪，请先🌟

• https://github.com/ten-framework/ten-framework

• https://github.com/ten-framework/ten-vad

• https://github.com/ten-framework/ten-turn-detection

• https://github.com/ten-framework/portal

HuggingFace Space 可直接体验打断模型

• https://huggingface.co/spaces/TEN-framework/ten-agent-demo

TEN Agent 可直接体验实时多模态和端到端

• https://agent.theten.ai 

官网，文档和 blog

• https://theten.ai

Discord

• https://discord.gg/VnPftUzAMJ

X/推特

• https://x.com/TenFramework

• https://x.com/elliotchen100

TEN 视频系列

• https://space.bilibili.com/501199591

小红书

• https://shorturl.at/QvhQv

 

## 项目运行记录

账号注册， 送了10000分钟额度

https://console.shengwang.cn/overview



![8e16c91150f5b93e225b5afecb1cfc65](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\8e16c91150f5b93e225b5afecb1cfc65.png)

![ef6dfc75953b91b182bfab64fcfe54be](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\ef6dfc75953b91b182bfab64fcfe54be.png)

![2e28ff202545718b4cc543c5be93d097](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\2e28ff202545718b4cc543c5be93d097.png)

![2505e7063930546db700095e0394d6c6](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\2505e7063930546db700095e0394d6c6.png)



### 使用默认值构建代理graph（约 5 分钟 - 约 8 分钟）

构建失败

![image-20251020151142820](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\image-20251020151142820.png)

### 使用docker构建（230）

```
cd /data/metahuman_work/ten-framework/ai_agents
# Build image
nohup docker build -f agents/examples/voice-assistant/Dockerfile -t voice-assistant-app . > build-ai-agents.log 2>&1 &
# Run
docker run --rm -it --env-file .env -p 8080:8080 -p 3000:3000 voice-assistant-app

# voice-assistant-live2d
cd /data/metahuman_work/ten-framework/ai_agents
nohup docker build -f agents/examples/voice-assistant-live2d/Dockerfile -t voice-assistant-live2d . > build-voice-assistant-live2d.log 2>&1 &
```

需要在容器内部配置1pip代理，2替换ubuntu的源，替换 goproxy代理， 配置tman代理， 配置



### 使用docker运行voice-assistant

```
docker exec -it ten_agent_dev bash
cd /app/agents/examples/voice-assistant
task -t Taskfile.docker2.yml run-prod

# 输出
task: [run-frontend-prod] npm start
task: [run-gd-server] tman designer
task: [run-api-server] ./bin/api -tenapp_dir=/app/agents/examples/voice-assistant/tenapp

```

Taskfile.docker2.yml文件内容

```
version: "3"
dotenv: [".env"]
tasks:
  run-api-server:
    desc: run api server
    dir: ../../../server
    cmds:
      - ./bin/api -tenapp_dir={{.PWD}}/tenapp
  run-frontend-prod:
    desc: run frontend in production
    dir: ./playground
    cmds:
      - npm start
    background: true
  run-gd-server:
    desc: run tman dev http server for TMAN Designer
    dir: ./tenapp
    cmds:
      - tman designer
  run-prod:
    desc: run both api and frontend in production
    deps:
      - task: run-gd-server
      - task: run-api-server
      - task: run-frontend-prod
```

#### 提交镜像

```
docker commit --author "zhoujing <121531845@qq.com>" --message "Added Python dependencies and configurations" 635251ac7444 ten_voice_assistant_dev:latest
```





## linux运行和配置clash并为Docker容器设置代理



https://zhuanlan.zhihu.com/p/1925152773210642048



获取配置文件

portal.shadowsocks.nz

![image-20251021100311404](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\image-20251021100311404.png)

![image-20251021100256469](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\image-20251021100256469.png)

![image-20251021100329016](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\image-20251021100329016.png)





clash 的目录  `/data/metahuman_work/clash` 

配置文件位置`~/.config/clash/` , 修改配置文件

![image-20251021202646309](G:\metahuman_work\OpenAvatarChat\OpenAvataChat_quick_start.assets\image-20251021202646309.png)

运行clash`nohup ./clash-linux-amd64 > clash.log 2>&1 &`



使用代理，直接配置环境变了

```
export https_proxy=http://127.0.0.1:7890 
export http_proxy=http://127.0.0.1:7890 
# 注意是 7891
export all_proxy=socks5://127.0.0.1:7891
```



### 在docker容器内部配置代理

为docker配置代理, 这段配置是**为 Docker 容器内部设置代理**,让容器能够通过宿主机的 Clash 代理访问网络。

```
# 主机执行
ip addr show docker0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1
# 输出
172.17.0.1
```

容器内配置

```
# 进入容器
docker exec -it ten_agent_dev bash
# 配置环境变量
export https_proxy=http://172.17.0.1:7890
export http_proxy=http://172.17.0.1:7890
export all_proxy=http://172.17.0.1:789

# 容器内测试
wget www.google.com
# 输出
--2025-10-21 02:25:42--  http://www.google.com/
Connecting to 172.17.0.1:7890... connected.
Proxy request sent, awaiting response... 200 OK
Length: unspecified [text/html]
Saving to: 'index.html'
index.html [ <=> ]  18.19K   107KB/s    in 0.2s    
2025-10-21 02:25:43 (107 KB/s) - 'index.html' saved [18627]
# 输出结束
```



运行端口映射

```powershell
ssh -L 3010:localhost:3010 -o ServerAliveInterval=60 user@192.168.8.230

ssh -L 3010:localhost:3010 -o ServerAliveInterval=60 user@192.168.8.230
```



[Live2D文档](https://docs.live2d.com/)