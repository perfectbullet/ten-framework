#!/bin/bash

# 切换到脚本所在目录
cd "$(dirname "$0")"

# PID 文件
PID_FILE=".voice_assistant.pid"
LOG_FILE="info.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取运行中的进程 PID
get_running_pid() {
    # 检查通过 tman/task run 启动的进程
    # 优先查找 bin/api 进程（实际运行的 API 服务器）
    local pid=$(pgrep -f "bin/api.*voice-assistant" | head -1)

    # 如果没找到，尝试查找 bin/main 进程
    if [ -z "$pid" ]; then
        pid=$(pgrep -f "bin/main.*voice-assistant" | head -1)
    fi

    # 如果没找到，尝试匹配 tenapp 目录路径
    if [ -z "$pid" ]; then
        pid=$(pgrep -f "tenapp_dir=.*voice-assistant" | head -1)
    fi

    # 如果没找到，尝试其他可能的模式
    if [ -z "$pid" ]; then
        pid=$(pgrep -f "tman run start" | head -1)
    fi

    if [ -z "$pid" ]; then
        pid=$(pgrep -f "task run" | head -1)
    fi

    echo "$pid"
}

# 检查服务是否正在运行
is_running() {
    local pid=$(get_running_pid)
    if [ -n "$pid" ]; then
        # 检查进程是否真的存在
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 停止服务
stop_service() {
    echo "====================================="
    echo "Voice Assistant 停止服务"
    echo "====================================="

    if ! is_running; then
        print_warn "服务未运行"
        return 0
    fi

    local pid=$(get_running_pid)
    print_info "正在停止服务 (PID: $pid)..."

    # 优雅停止
    kill "$pid" 2>/dev/null

    # 等待进程结束（最多 5 秒）
    local count=0
    while is_running && [ $count -lt 50 ]; do
        sleep 0.1
        count=$((count + 1))
    done

    # 如果还没结束，强制杀死
    if is_running; then
        print_warn "服务未响应，强制终止..."
        pkill -f "task run" 2>/dev/null
        pkill -f "./bin/api" 2>/dev/null
        pkill -f "bin/main" 2>/dev/null
        sleep 1
    fi

    # 清理 PID 文件
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"

    print_info "服务已停止"
}

# 清理临时文件
clean_temp_files() {
    echo ""
    print_info "清理临时文件..."

    local total_cleaned=0

    # 清理 send_audio_save 目录
    if [ -d "./tenapp/send_audio_save" ]; then
        COUNT=$(find ./tenapp/send_audio_save -type f \( -name "*.pcm" -o -name "*.wav" \) 2>/dev/null | wc -l)
        if [ "$COUNT" -gt 0 ]; then
            find ./tenapp/send_audio_save -type f \( -name "*.pcm" -o -name "*.wav" \) -delete 2>/dev/null
            print_info "  清理 send_audio_save: $COUNT 个音频文件"
            total_cleaned=$((total_cleaned + COUNT))
        fi
    fi

    # 清理 vad_dump 目录 (包括可能很大的 pcm 文件)
    if [ -d "./tenapp/vad_dump" ]; then
        # 清理所有文件，包括可能很大的 pcm 文件
        COUNT=$(find ./tenapp/vad_dump -type f 2>/dev/null | wc -l)
        if [ "$COUNT" -gt 0 ]; then
            find ./tenapp/vad_dump -type f -delete 2>/dev/null
            print_info "  清理 vad_dump: $COUNT 个文件"
            total_cleaned=$((total_cleaned + COUNT))
        fi
    fi

    # 清理 msg_dict_json 目录
    if [ -d "./tenapp/msg_dict_json" ]; then
        COUNT=$(find ./tenapp/msg_dict_json -type f -name "*.json" 2>/dev/null | wc -l)
        if [ "$COUNT" -gt 0 ]; then
            find ./tenapp/msg_dict_json -type f -name "*.json" -delete 2>/dev/null
            print_info "  清理 msg_dict_json: $COUNT 个 json 文件"
            total_cleaned=$((total_cleaned + COUNT))
        fi
    fi

    if [ "$total_cleaned" -eq 0 ]; then
        print_info "  无临时文件需要清理"
    else
        print_info "  共清理 $total_cleaned 个文件"
    fi
}

# 启动服务
start_service() {
    echo "====================================="
    echo "Voice Assistant 启动服务"
    echo "====================================="

    # 检查是否已经在运行
    if is_running; then
        local pid=$(get_running_pid)
        print_error "服务已在运行 (PID: $pid)"
        echo "请先使用 '$0 stop' 停止服务，或使用 '$0 restart' 重启"
        return 1
    fi

    # 设置环境变量
    print_info "设置环境变量..."
    export AGORA_APP_ID=30613432523348989b9d2bf4110f90a0
    export AGORA_APP_CERTIFICATE=713297dd65034d2dac28485af2b7357b
    # export OPENAI_API_BASE=http://192.168.8.233:11434/v1
    # export OPENAI_MODEL=qwen2.5:14b

    export OPENAI_BASE_URL=http://192.168.8.233:11434/v1
    export OPENAI_MODEL=qwen2.5:14b

    export EMPLOYEE_API_BASE_URL=http://192.168.8.233:8100

    # 后台启动
    print_info "启动服务..."
    nohup task run > "$LOG_FILE" 2>&1 &
    local bg_pid=$!

    # 保存后台进程 PID（用于追踪）
    echo "$bg_pid" > "$PID_FILE"

    # 等待服务启动
    print_info "等待服务启动..."
    sleep 3

    # 使用 get_running_pid 获取实际服务进程的 PID
    local service_pid=$(get_running_pid)

    if [ -n "$service_pid" ]; then
        print_info "服务已成功启动"
        echo ""
        echo "====================================="
        echo "服务信息"
        echo "====================================="
        echo "  服务 PID:   $service_pid"
        echo "  日志文件:   $LOG_FILE"
        echo "  查看日志:   tail -f $LOG_FILE"
        echo ""
        echo "管理命令:"
        echo "  停止服务:   $0 stop"
        echo "  重启服务:   $0 restart"
        echo "  查看状态:   $0 status"
        echo "====================================="
    else
        print_error "服务启动失败，请检查日志: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 显示状态
show_status() {
    echo "====================================="
    echo "Voice Assistant 服务状态"
    echo "====================================="

    if is_running; then
        local pid=$(get_running_pid)
        print_info "服务正在运行"
        echo "  PID: $pid"
        echo "  运行时间: $(ps -p "$pid" -o etime= 2>/dev/null | xargs)"
        echo "  内存使用: $(ps -p "$pid" -o rss= 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')"

        # 检查日志文件大小
        if [ -f "$LOG_FILE" ]; then
            local log_size=$(du -h "$LOG_FILE" | cut -f1)
            echo "  日志大小: $log_size"
        fi
    else
        print_warn "服务未运行"
    fi

    # 检查临时文件大小
    echo ""
    print_info "临时文件统计:"

    if [ -d "./tenapp/vad_dump" ]; then
        local vad_size=$(du -sh ./tenapp/vad_dump 2>/dev/null | cut -f1)
        local vad_files=$(find ./tenapp/vad_dump -type f 2>/dev/null | wc -l)
        echo "  vad_dump: $vad_size ($vad_files 个文件)"
    fi

    if [ -d "./tenapp/send_audio_save" ]; then
        local audio_size=$(du -sh ./tenapp/send_audio_save 2>/dev/null | cut -f1)
        local audio_files=$(find ./tenapp/send_audio_save -type f 2>/dev/null | wc -l)
        echo "  send_audio_save: $audio_size ($audio_files 个文件)"
    fi
    echo "====================================="
}

# 重启服务
restart_service() {
    echo "====================================="
    echo "Voice Assistant 重启服务"
    echo "====================================="
    echo ""

    # 先停止
    stop_service
    echo ""

    # 等待一下确保资源释放
    sleep 1

    # 清理临时文件（可选）
    if [ "$1" == "--clean" ]; then
        clean_temp_files
        echo ""
    fi

    # 再启动
    start_service
}

# 显示帮助
show_help() {
    echo "Voice Assistant 管理脚本"
    echo ""
    echo "用法: $0 {start|stop|restart|status|clean|help}"
    echo ""
    echo "命令:"
    echo "  start    - 启动服务"
    echo "  stop     - 停止服务"
    echo "  restart  - 重启服务"
    echo "  status   - 显示服务状态"
    echo "  clean    - 清理临时文件（服务必须先停止）"
    echo "  help     - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start           # 启动服务"
    echo "  $0 stop            # 停止服务"
    echo "  $0 restart         # 重启服务"
    echo "  $0 restart --clean # 重启并清理临时文件"
    echo "  $0 status          # 查看状态"
    echo ""
}

# 清理命令（独立使用）
clean_only() {
    if is_running; then
        print_error "服务正在运行，请先停止服务后再清理临时文件"
        echo "使用 '$0 stop' 停止服务，或使用 '$0 restart --clean' 重启并清理"
        return 1
    fi

    echo "====================================="
    echo "清理临时文件"
    echo "====================================="
    clean_temp_files
    echo "====================================="
}

# 主函数
case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service "$2"
        ;;
    status)
        show_status
        ;;
    clean)
        clean_only
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "未知命令: ${1:-}"
        echo ""
        show_help
        exit 1
        ;;
esac
