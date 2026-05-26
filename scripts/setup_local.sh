#!/usr/bin/env bash
# Install Ollama and pull a local model so news_lens can run with no
# subscriptions and no network calls beyond fetching the news articles
# themselves.
#
# Usage:
#   bash scripts/setup_local.sh                    # default: qwen3:8b
#   bash scripts/setup_local.sh qwen3:4b           # low-RAM machines
#   bash scripts/setup_local.sh qwen2.5:14b        # if you have 16GB+
#
# Choosing a model:
#   qwen3:4b        ~3.0 GB RAM   smallest model that handles nested JSON schemas reliably
#   qwen3:8b        ~5.0 GB RAM   recommended default; best quality-per-GB
#   qwen2.5:14b     ~8.7 GB RAM   meaningful quality bump
#   qwen2.5:32b     ~20  GB RAM   approaches hosted-Claude quality
#
# Llama 3.x at 8B and below tends to echo the JSON schema back instead of
# filling it in, which breaks extraction and alignment. Stick with Qwen
# locally, or use Llama 70B-class only on hosted endpoints.
#
# After this script finishes, run:
#   python -m news_lens URL1 URL2 URL3 --ollama --html out.html

set -euo pipefail

MODEL="${1:-qwen3:8b}"

if ! command -v ollama >/dev/null 2>&1; then
    echo "Installing Ollama..."
    case "$(uname -s)" in
        Linux)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                brew install ollama
            else
                echo "Homebrew not found. Download Ollama from https://ollama.com/download" >&2
                exit 1
            fi
            ;;
        *)
            echo "Unsupported OS. Install Ollama manually from https://ollama.com/download" >&2
            exit 1
            ;;
    esac
else
    echo "Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
fi

# Start the Ollama server in the background if it isn't already running.
if ! curl -sS --max-time 2 http://localhost:11434/ >/dev/null 2>&1; then
    echo "Starting Ollama server in the background..."
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    # Wait up to 20 seconds for the server to come up.
    for _ in $(seq 1 20); do
        if curl -sS --max-time 1 http://localhost:11434/ >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

if ! curl -sS --max-time 2 http://localhost:11434/ >/dev/null 2>&1; then
    echo "Ollama server failed to start. Check /tmp/ollama.log for details." >&2
    exit 1
fi

echo "Pulling model: $MODEL"
ollama pull "$MODEL"

echo
echo "Ready. Ollama is serving $MODEL at http://localhost:11434/v1"
echo
echo "Strongly recommended (deterministic alignment + topical search clustering):"
echo "  pip install -e \".[local-llm,embeddings]\""
echo
echo "Then run the pipeline with:"
echo "  python -m news_lens URL1 URL2 URL3 --ollama --model $MODEL --html out.html"
