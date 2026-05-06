#!/usr/bin/env bash
# Install Ollama and pull a local model so news_lens can run with no
# subscriptions and no network calls beyond fetching the news articles
# themselves.
#
# Usage:
#   bash scripts/setup_local.sh                    # default: llama3.2:3b
#   bash scripts/setup_local.sh llama3.1:8b        # if you have 8GB+ free RAM
#   bash scripts/setup_local.sh qwen2.5:14b        # if you have 16GB+
#
# Choosing a model:
#   llama3.2:1b     ~1.3 GB RAM   smallest, lowest quality, good for testing
#   llama3.2:3b     ~2.0 GB RAM   recommended default; runs anywhere
#   gemma2:2b       ~1.6 GB RAM   strong for size
#   qwen2.5:7b      ~4.4 GB RAM   strong reasoner; 8GB+ machines
#   llama3.1:8b     ~4.7 GB RAM   the recommended quality target
#   qwen2.5:14b     ~8.7 GB RAM   meaningful quality bump
#   llama3.1:70b    ~40 GB RAM    needs a real GPU
#
# After this script finishes, run:
#   python -m news_lens URL1 URL2 URL3 --ollama --html out.html

set -euo pipefail

MODEL="${1:-llama3.2:3b}"

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
echo "Run the pipeline with:"
echo "  python -m news_lens URL1 URL2 URL3 --ollama --model $MODEL --html out.html"
