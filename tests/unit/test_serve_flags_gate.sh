#!/bin/bash
# serve_flags_gate 判别力回归：R1-R7 反向用例（不需要活栈）
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
"$ROOT/tools/serve_flags_gate.sh" --self-test
