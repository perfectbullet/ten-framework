#!/bin/bash
# Filter [tts] lines from a log file into a new file with '-tts' suffix
# Usage: ./filter_tts_log.sh <logfile>
# Example: ./filter_tts_log.sh info-下午测试-我测试语音合成.log

if [ $# -lt 1 ]; then
    echo "Usage: $0 <logfile>"
    exit 1
fi

input="$1"
if [ ! -f "$input" ]; then
    echo "File not found: $input"
    exit 1
fi

# info-xxx.log -> info-xxx-tts.log
base="${input%.log}"
output="${base}-tts.log"

grep '\[tts\]' "$input" > "$output"
echo "Filtered $(wc -l < "$output") lines -> $output"
