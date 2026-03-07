#!/bin/bash
set -euo pipefail

# ================================
# Global Configurations
# ================================
export CUDA_VISIBLE_DEVICES=0

output_root="results/random"
apollo_root="/data/d/mingfeicheng/github/common/apollo"
fuzzer_dir="fuzzer/random"
debug=true
resume=true
save_record=true
sandbox_image="drivora/sandbox:latest"
sandbox_fps=20.0
time_budget=6  # hours
use_dreamview=false

# ================================
# Tester Configurations
# ================================
tester_type="random"
tester_config_lst=("s1")
run_indices=(1)

# ================================
# Main Loop
# ================================
for run_index in "${run_indices[@]}"; do
  for tester_cfg in "${tester_config_lst[@]}"; do
  
    tester_config_path="${fuzzer_dir}/configs/${tester_cfg}.yaml"

    run_tag="${tester_type}_${tester_cfg}_run${run_index}" # NOTE: can not too long
    apollo_tag="${tester_type}"
    attempt=1

    echo ""
    echo "===================================================="
    echo "▶️  Start Run: tester=${tester_cfg}, run=${run_index}"
    echo "▶️  Run Tag : $run_tag"
    echo "===================================================="
    echo ""

    while true; do
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ▶️ Attempt $attempt ..."

      set +e  # Allow failures for retry
      python start_fuzzer.py \
        debug="$debug" \
        output_root="$output_root" \
        apollo_root="$apollo_root" \
        run_tag="$run_tag" \
        debug="$debug" \
        resume="$resume" \
        save_record="$save_record" \
        sandbox_image="$sandbox_image" \
        sandbox_fps="$sandbox_fps" \
        tester.type="$tester_type" \
        tester.time_budget="$time_budget" \
        tester.config_path="$tester_config_path" \
        fuzzer_dir="$fuzzer_dir" \
        apollo_tag="$apollo_tag" \
        use_dreamview="$use_dreamview"

      exit_code=$?
      set -e  # Re-enable strict mode

      if [[ $exit_code -eq 0 ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Success."
        break
      fi

      echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Crash (exit $exit_code)."

      if [[ $attempt -ge $max_retries ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Max retries reached ($max_retries). Abort."
        break
      fi

      echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔁 Retry in $retry_delay seconds..."
      sleep $retry_delay
      ((attempt++))
    done

  done
done
