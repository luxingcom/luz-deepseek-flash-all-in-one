#!/bin/bash
# gw-verify — 并发网关验证器（六探针+离线配置 lint；TOOLS31 §二 P4-3）
#
# 【探针（--live；执行窗面）】
#   P1 401 面：无 key 打 /gw/* 必拒（GW_API_KEY Bearer 鉴权工作）。**rc3.8.5 起
#     （AUTH-DEPLOY-20261014）全局门 GW_REQUIRE_AUTH=1 在役：无 key 业务 POST 也
#     必 401（门在统一分流层、body/上游之前——本地应答零上游推理载，原「会真触发
#     一次上游推理」的误断言撤回依据已消）——P1 增业务面断言（rc≤3.8.4 无钥=200
#     旧态，P1 业务面=Mac 在役面预期）。
#   P2 429 面：>MAX_CONCURRENCY 并发 POST 必限流（信号量工作）。A4 修正：GET/HEAD 在
#     dispatch 免并发槽（proxy :759-766，信号量之前返回）——health 打点永不 429，
#     信号量验证必须 POST 面（窗口专用打点序见 --live 输出）。
#   P3 直连对照：绕网关直抵上游 health（8899 直达=基线对照，轻探零推理载荷）
#   P4 健康穿透：/health 经网关必 200（透传工作；rc3.8.5 /health=鉴权豁免面）
#   P5 上游失效面：上游停时网关 502/错误帧行为——演练窗专用（本件零执行）
#   P6 模型门面（GW_KEY 在时）：带 key + 假模型名 POST → 404 model_not_found
#     （rc3.8.5 GW_ALLOWED_MODELS 白名单；本地应答零上游推理载）。带 key + 真模型
#     =一发定谳（执行窗面，本件零执行）。
#   P7 容量广播面（GW_KEY 在时；rc3.8.6 ②-a/A10）：带 key GET /v1/models →
#     条目带 context_window 时四键==max_model_len 才绿（含 limit.context）；
#     条目不带该键=广播未开/未部署（ADVERTISE_MODEL_CAPACITY=0 面）→ INFO 跳过
#     不红（缺省关为包缺省语义）。本地对 8001 名录面轻探，零推理载荷。
# 【离线面（--offline；案头）】配置 lint：UPSTREAM 形合法/MAX_CONCURRENCY 域 [1,64]/
#   PORT 域 [1,65535]/GW_API_KEY 非空（键面非空律——空=裸奔面=红）+B4 域检查
#   （QUEUE_TIMEOUT [1,300]/DEDUP_ENABLE {0,1}/INJECT_ENABLE_THINKING {0,1}，键在才查）
#   +rc3.8.6 域检查（ADVERTISE_MODEL_CAPACITY {0,1}/MODELS_CONTEXT_LEN ≥0 整数，键在才查）
#   +#45614 面（sglang issue #45614 host 侧规避执法，2026-10-30）：SGLANG_DEFAULT_THINKING
#   属引擎侧 env、对网关为异键——env 文件内任何声明（无论真假值）=红（该键真值是
#   上游「prompt 侧读/解析侧不读」不对称泄漏的触发面，异键混入=误植种子）；主车道
#   （第一实参）INJECT_ENABLE_THINKING 必须=1——裸请求双键注入（rc3.8.8 thinking+
#   enable_thinking）是缺陷的网关侧兜底，缺键/=0=兜底敞开=红；vl 车道（第二实参）
#   维持域检查 {0,1}（VL 呈裁 C3 形=0 不适用注入律）
#   +unit/drop-in 模板 lint（v2+vl 双 unit——要件在+密钥值零携带=SMOK_KEY 律执法；
#   vl env 文件可作第二实参同面 lint）。
# 【出口】0=绿/1=红/2=无法判（--live 网关不可达=2，ANCHOR-UNKNOWN 语义）。
# 【红线】--live=执行窗面（产线在役时 P2/P5 先呈裁）；探针载荷=最小面（/gw/* 401 拒答
#   与 health 探测零上游推理载——P1 收敛后成立；业务路径 POST 探测=误断言已撤，零执行）。
# 【Mac 变体（AUTH-DEPLOY-20261014 起=在役本尊 rc3.8.5；GW-PATCH-20261015 升 rc3.8.6）】
#   网关本尊=Mac mini M6 OrbStack 容器 concurrency-proxy-v2-mac :8001（GW_REQUIRE_AUTH=1：
#   /v1/* 与 /metrics 一切方法收 Bearer GW_API_KEY；/health 豁免=guardctl 探针面；
#   GW_ALLOWED_MODELS=deepseek-v4.1-flash 模型门；**rc3.8.6 容量广播 ADVERTISE_MODEL_
#   CAPACITY=1+MODELS_CONTEXT_LEN=0**=四键取引擎真值）；**8002 VL 车道已撤除**（G1 §E
#   零消费者；compose .bak-auth1014 留回退）；**8003=responses-gateway-mac 鉴权
#   公共入口**（02 v2.2.1 容器化迁 Mac，API_KEY 客户端钥同值平移；GW-PATCH 窗 v2.2.2
#   起名录面并带容量四键）。用法面：--live 自 01 打 GW_URL=http://<mac-if-ip>:8001；
#   GW_KEY=<GW_API_KEY 值> 在时增 P6 模型门+P7 容量广播带钥探针（值经 env 传递，
#   绝不入档）；P3「直连对照」改义=UP_URL 指 -R 隧道面 http://<mac-gw-ip>:24001（既有
#   在役只读探针类，Mac 侧无本地 8899 可直；**8899 直打禁律不变**；⚠ 2026-10-15
#   net-rebuild 后该隧道靶 192.168.5.18x 已失效=Mac 链疑断呈裁 P6 既有位，探针红
#   非本件引入）；P1/P4 语义原样。本件默认值仍留 01 本地形态（127.0.0.1）＝历史基线，
#   Mac 部署节见包 README。
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$HERE/../_lib/verdict.sh" ] && . "$HERE/../_lib/verdict.sh"

GW_URL="${GW_URL:-http://127.0.0.1:8001}"
UP_URL="${UP_URL:-http://127.0.0.1:8899}"
GW_KEY="${GW_KEY:-}"          # rc3.8.5 带钥面（P6 模型门探针用；值零入档）

lint_env() {  # lint_env <env 文件> [main|vl] → 0/1（四键面+#45614 面全绿才 0；车道缺省=main）
  local f="$1" v
  [ -r "$f" ] || return 1
  v=$(grep -E '^UPSTREAM=' "$f" | head -1)
  printf '%s' "$v" | grep -qE '^UPSTREAM=http://[0-9a-zA-Z.:/-]+$' || return 1
  v=$(grep -E '^MAX_CONCURRENCY=' "$f" | head -1 | cut -d= -f2)
  [ "$v" -ge 1 ] 2>/dev/null && [ "$v" -le 64 ] 2>/dev/null || return 1
  v=$(grep -E '^PORT=' "$f" | head -1 | cut -d= -f2)
  [ "$v" -ge 1 ] 2>/dev/null && [ "$v" -le 65535 ] 2>/dev/null || return 1
  v=$(grep -E '^GW_API_KEY=' "$f" | head -1 | cut -d= -f2)
  [ -n "$v" ] && [ "$v" != '<值位空——部署窗填入，绝不入包>' ] || return 1
  # #45614 异键律（2026-10-30）：SGLANG_DEFAULT_THINKING=引擎侧 env，网关 env 内
  #   任何声明（含 =0 假形）=红——真值是上游泄漏触发面、假形是误植种子，一律不得入。
  grep -qE '^(export +)?SGLANG_DEFAULT_THINKING=' "$f" && return 1
  # B4 域检查（键在才查——缺键=脚本默认继承非红面；A2/A3 补键后的 typo/越域执法面）
  v=$(grep -E '^QUEUE_TIMEOUT=' "$f" | head -1 | cut -d= -f2)
  if [ -n "$v" ]; then { [ "$v" -ge 1 ] && [ "$v" -le 300 ]; } 2>/dev/null || return 1; fi
  v=$(grep -E '^DEDUP_ENABLE=' "$f" | head -1 | cut -d= -f2)
  if [ -n "$v" ]; then [ "$v" = 0 ] || [ "$v" = 1 ] || return 1; fi
  # INJECT_ENABLE_THINKING：主车道必须 =1（#45614 裸请求双键兜底缺省开=部署红线；
  #   vl 车道维持 {0,1} 域检查——VL 呈裁 C3 形=0）
  v=$(grep -E '^INJECT_ENABLE_THINKING=' "$f" | head -1 | cut -d= -f2)
  if [ "${2:-main}" = main ]; then
    [ "$v" = 1 ] || return 1
  else
    if [ -n "$v" ]; then [ "$v" = 0 ] || [ "$v" = 1 ] || return 1; fi
  fi
  # rc3.8.6 域检查（键在才查——容量广播两键；缺键=脚本默认关/引擎实值非红面）
  v=$(grep -E '^ADVERTISE_MODEL_CAPACITY=' "$f" | head -1 | cut -d= -f2)
  if [ -n "$v" ]; then [ "$v" = 0 ] || [ "$v" = 1 ] || return 1; fi
  v=$(grep -E '^MODELS_CONTEXT_LEN=' "$f" | head -1 | cut -d= -f2)
  if [ -n "$v" ]; then { [ "$v" -ge 0 ]; } 2>/dev/null || return 1; fi
  return 0
}

lint_unit() {  # lint_unit <unit 文件> → 0/1（要件在+密钥值零携带）
  local f="$1"
  [ -r "$f" ] || return 1
  grep -q '^ExecStart=.*concurrency_proxy_v2.py' "$f" || return 1
  grep -q '^EnvironmentFile=' "$f" || return 1
  grep -q '^Restart=' "$f" || return 1
  grep -qE '(^Environment=.*GW_API_KEY=|^GW_API_KEY=).+' "$f" && return 1
  return 0
}

lint_dropin() {  # lint_dropin <conf> → 0/1
  local f="$1"
  [ -r "$f" ] || return 1
  grep -q '^\[Service\]' "$f" || return 1
  grep -qE '^(MemoryMax|NoNewPrivileges)=' "$f" || return 1
  return 0
}

cmd="${1:-}"; shift || true
case "$cmd" in
  --offline)
    ENVF="${1:-}"; VLENVF="${2:-}"
    [ -z "$ENVF" ] && { echo "用法：$0 --offline <已填值 env 文件> [已填值 vl env 文件]（模板件=预期红，见 --selfcheck T2/T6）" >&2; exit 2; }
    vr_begin
    lint_env "$ENVF" main || vr_face "config-lint" "$ENVF 键面非空律/域违约/#45614 面（UPSTREAM 形/MAX_CONCURRENCY [1,64]/PORT/GW_API_KEY 非空/QUEUE_TIMEOUT [1,300]/DEDUP {0,1}/SGLANG_DEFAULT_THINKING 异键禁入/**主车道 INJECT_ENABLE_THINKING 必须=1**）"
    if [ -n "$VLENVF" ]; then   # B4：VL 车道 env 双件 lint 面（缺省=只 lint 主车道）；#45614：vl 车道 INJECT 维持域检查 {0,1}（呈裁 C3 形=0）
      lint_env "$VLENVF" vl || vr_face "vl-config-lint" "$VLENVF 键面非空律/域违约（同主车道键面+SGLANG_DEFAULT_THINKING 异键禁入；INJECT {0,1} 域检查）"
    fi
    lint_unit "$HERE/payload/units/concurrency-proxy-v2.service" || vr_face "unit-lint" "concurrency-proxy-v2.service 要件缺或密钥值入 unit"
    lint_unit "$HERE/payload/units/concurrency-proxy-vl.service" || vr_face "vl-unit-lint" "concurrency-proxy-vl.service 要件缺或密钥值入 unit"
    lint_dropin "$HERE/payload/units/10-gateway-hardening.conf" || vr_face "dropin-lint" "10-gateway-hardening.conf 面缺"
    vr_suggest "红面逐项按 payload/env 模板与 units 注记修；GW_API_KEY 值只入宿主 0600 件" "gateway#offline" manual
    vr_emit ;;
  --live)
    vr_begin; vr_suggest "探针红面处置见 GATEWAY-MIGRATION-PLAN-20261007 §〇/P0 面" "gateway#live" manual
    command -v curl >/dev/null 2>&1 || { vr_unknown "curl-missing" "无 curl"; vr_emit; }
    # P4 健康穿透（经网关）
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$GW_URL/health" 2>/dev/null)
    if [ "$code" = 200 ]; then echo "[gw-verify] P4 健康穿透绿（/health 经网关 200）"
    else vr_face "P4-health-passthrough" "code=${code:-unreachable}"; fi
    # P1 401 面：管理面 /gw/*（本地应答零上游载）
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$GW_URL/gw/health" 2>/dev/null)
    case "$code" in
      401) echo "[gw-verify] P1 401 面绿（/gw/health 无 key 拒 401=GW_API_KEY Bearer 鉴权工作）" ;;
      000) vr_unknown "P1-unreachable" "网关不可达（$GW_URL）" ;;
      200) vr_face "P1-auth" "/gw/health 无 key 得 200=GW_API_KEY 未设（管理面裸奔——键面非空律红）" ;;
      *)   vr_face "P1-auth" "/gw/health 无 key code=$code（预期 401）" ;;
    esac
    # P1b 业务面 401（rc3.8.5 GW_REQUIRE_AUTH=1 在役面；门在 body/上游之前——本地
    # 应答零上游推理载。rc≤3.8.4 无钥=200 旧态=此断言的预期差，Mac 在役面恒 401）
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
      -X POST "$GW_URL/v1/chat/completions" -H 'Content-Type: application/json' \
      -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' 2>/dev/null)
    if [ "$code" = 401 ]; then
      echo "[gw-verify] P1b 业务面 401 绿（无 key POST /v1/chat/completions 拒 401=GW_REQUIRE_AUTH 全局门工作）"
    elif [ "$code" = 200 ]; then
      vr_face "P1b-auth" "无 key 业务 POST 得 200=GW_REQUIRE_AUTH 未开（业务面裸奔——rc3.8.5 部署红）"
    else
      vr_face "P1b-auth" "无 key 业务 POST code=${code:-unreachable}（预期 401）"
    fi
    # P6 模型门面（GW_KEY 在时；本地应答零上游推理载；真模型一发=执行窗面零执行）
    if [ -n "$GW_KEY" ]; then
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        -X POST "$GW_URL/v1/chat/completions" -H 'Content-Type: application/json' \
        -H "Authorization: Bearer $GW_KEY" \
        -d '{"model":"no-such-model-zzz","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' 2>/dev/null)
      if [ "$code" = 404 ]; then
        echo "[gw-verify] P6 模型门绿（带 key+假模型 404 model_not_found=GW_ALLOWED_MODELS 白名单工作）"
      else
        vr_face "P6-model" "带 key+假模型 code=${code:-unreachable}（预期 404）"
      fi
    else
      echo "[gw-verify] P6 模型门=GW_KEY 未设，跳过（带钥面探针需 GW_KEY env）"
    fi
    # P7 容量广播面（rc3.8.6 ②-a；GW_KEY 在时）：/v1/models 条目带 context_window
    # 时四键==max_model_len 才绿；不带=广播未开/未部署 → INFO 跳过不红（缺省关语义）。
    if [ -n "$GW_KEY" ]; then
      mbody=$(curl -s --max-time 10 -H "Authorization: Bearer $GW_KEY" \
        "$GW_URL/v1/models" 2>/dev/null)
      p7=$(printf '%s' "$mbody" | python3 -c '
import json,sys
try: doc=json.load(sys.stdin)
except Exception: print("PARSE_FAIL"); sys.exit(0)
ents=doc.get("data") if isinstance(doc,dict) else None
if not isinstance(ents,list) or not ents: print("NO_ENTRIES"); sys.exit(0)
withcap=[e for e in ents if isinstance(e,dict) and "max_model_len" in e]
if not withcap: print("NO_CAP_ENTRY"); sys.exit(0)
if not any("context_window" in e for e in withcap):
    print("OFF"); sys.exit(0)
bad=[]
for e in withcap:
    n=e.get("max_model_len"); lim=e.get("limit")
    if not (e.get("context_length")==n and e.get("context_window")==n
            and e.get("max_input_tokens")==n
            and isinstance(lim,dict) and lim.get("context")==n):
        bad.append(str(e.get("id")))
print("BAD:"+",".join(bad) if bad else "OK")
' 2>/dev/null)
      case "$p7" in
        OK)      echo "[gw-verify] P7 容量广播绿（四键==max_model_len 全条目；②-a/A10 工作）" ;;
        OFF)     echo "[gw-verify] P7 容量广播=INFO 跳过（/v1/models 无 context_window=未开/未部署，ADVERTISE_MODEL_CAPACITY 缺省关面）" ;;
        BAD:*)   vr_face "P7-capacity" "容量广播四键≠max_model_len（${p7#BAD:}）——声明须恒=引擎真值" ;;
        ""|PARSE_FAIL|NO_ENTRIES|NO_CAP_ENTRY)
                 echo "[gw-verify] P7 容量广播=INFO 跳过（名录体不可判：${p7:-empty}；上游失效/无 max_model_len 条目不红）" ;;
        *)       echo "[gw-verify] P7 容量广播=INFO 跳过（${p7}）" ;;
      esac
    else
      echo "[gw-verify] P7 容量广播=GW_KEY 未设，跳过（带钥面探针需 GW_KEY env）"
    fi
    # P3 直连对照（上游 health 基线）
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$UP_URL/health" 2>/dev/null)
    if [ "$code" = 200 ]; then echo "[gw-verify] P3 直连对照绿（$UP_URL/health 200=基线在）"
    else vr_unknown "P3-upstream" "上游 health code=${code:-unreachable}（对照基线不可判）"; fi
    # P2 429 面=窗口专用打点序（A4 修正：GET/HEAD 在 dispatch 免并发槽（proxy :759-766，
    # 信号量之前返回）——health 打点永不 429，信号量验证必须 POST 面。
    # AUTH-DEPLOY-20261014：8002 VL 车道已撤除，梯=8001 单车道（Mac 在役 MAX_CONCURRENCY=16）
    echo "[gw-verify] P2 429 面=窗口专用（序：停写流→并发 POST /v1/chat/completions 打点"
    echo "[gw-verify]   〔stream 假 body max_tokens=1+Bearer GW_API_KEY（rc3.8.5 门后须带钥）；"
    echo "[gw-verify]   8001 梯 8→16→17〕→期待 N+1 发 429+Retry-After→/gw/metrics"
    echo "[gw-verify]   queue_wait/active_streams 收尾=0→复绿）"
    # P5 上游失效面=演练窗专用（零执行）
    echo "[gw-verify] P5 上游失效面=演练窗专用（停 8899 观察 502/错误帧族；本面零执行）"
    vr_emit ;;
  --selfcheck)
    rc=0; T=$(mktemp -d /tmp/gw-sc.XXXXXX)
    cp "$HERE/payload/env/gateway.env.template" "$T/good.env"
    sed -i 's|^GW_API_KEY=.*|GW_API_KEY=test-key-not-a-secret|' "$T/good.env"
    # T1 已填值 env lint 绿
    bash "$0" --offline "$T/good.env" 2>/dev/null | grep -q '"verdict":0' \
      && echo "[gw-verify][OK] T1 已填值 env lint 绿（verdict=0）" || { echo "[gw-verify][RED] T1 FAIL"; rc=1; }
    # T2 模板件（占位值）必红——键面非空律判别力
    out=$(bash "$0" --offline "$HERE/payload/env/gateway.env.template" 2>/dev/null); r=$?
    [ "$r" = 1 ] && printf '%s' "$out" | grep -q 'config-lint' \
      && echo "[gw-verify][OK] T2 占位模板判红（GW_API_KEY 空值=键面非空律）" || { echo "[gw-verify][RED] T2 FAIL（rc=$r）"; rc=1; }
    # T3 坏 UPSTREAM 必红
    sed 's|^UPSTREAM=.*|UPSTREAM=not-a-url|' "$T/good.env" > "$T/bad.env"
    bash "$0" --offline "$T/bad.env" 2>/dev/null | grep -q '"verdict":1' \
      && echo "[gw-verify][OK] T3 坏 UPSTREAM 判红" || { echo "[gw-verify][RED] T3 FAIL"; rc=1; }
    # T4 unit 密钥面：Environment 带密钥值必红（SMOK_KEY 律执法）
    { cat "$HERE/payload/units/concurrency-proxy-v2.service"; echo 'Environment=GW_API_KEY=leaked'; } > "$T/leak-unit.service"
    if lint_unit "$T/leak-unit.service"; then echo "[gw-verify][RED] T4 FAIL（密钥值入 unit 未判红）"; rc=1
    else echo "[gw-verify][OK] T4 unit 密钥值携带判红（SMOK_KEY 律执法）"; fi
    # T5 drop-in 面缺必红
    printf '[Service]\nStandardOutput=journal\n' > "$T/bad-dropin.conf"
    if lint_dropin "$T/bad-dropin.conf"; then echo "[gw-verify][RED] T5 FAIL"; rc=1
    else echo "[gw-verify][OK] T5 dropin 面缺判红"; fi
    # T6 VL 车道双件 lint 面（B4 补面）：vl unit 要件绿 + vl env 模板占位判红
    if lint_unit "$HERE/payload/units/concurrency-proxy-vl.service"; then
      echo "[gw-verify][OK] T6 vl unit lint 绿（要件在+密钥零携带）"
    else echo "[gw-verify][RED] T6 FAIL（vl unit 要件缺）"; rc=1; fi
    if lint_env "$HERE/payload/env/gateway-vl.env.template" vl; then
      echo "[gw-verify][RED] T6 FAIL（vl 模板占位未判红）"; rc=1
    else echo "[gw-verify][OK] T6 vl env 占位模板判红（GW_API_KEY 空值=键面非空律）"; fi
    # T7 域检查判别力（B4）：QUEUE_TIMEOUT 越域必红
    sed 's|^QUEUE_TIMEOUT=.*|QUEUE_TIMEOUT=9999|' "$T/good.env" > "$T/badq.env"
    if lint_env "$T/badq.env"; then echo "[gw-verify][RED] T7 FAIL（QUEUE_TIMEOUT 越域未判红）"; rc=1
    else echo "[gw-verify][OK] T7 QUEUE_TIMEOUT 越域判红（域 [1,300]）"; fi
    # T8 域检查判别力（rc3.8.6）：ADVERTISE_MODEL_CAPACITY 非 {0,1} 必红
    # （前置行法：lint 取 head -1 ⇒ 无论模板有无该键都命中红值行）
    { echo 'ADVERTISE_MODEL_CAPACITY=2'; cat "$T/good.env"; } > "$T/badadv.env"
    if lint_env "$T/badadv.env"; then echo "[gw-verify][RED] T8 FAIL（ADVERTISE_MODEL_CAPACITY=2 未判红）"; rc=1
    else echo "[gw-verify][OK] T8 ADVERTISE_MODEL_CAPACITY 越域判红（域 {0,1}）"; fi
    # T9 异键律判别力（#45614）：SGLANG_DEFAULT_THINKING 入网关 env 必红——真值形与
    #   假形同红（真值=上游泄漏触发面；假形=误植种子），engine 侧 env 不许混入网关面
    { cat "$T/good.env"; echo 'SGLANG_DEFAULT_THINKING=1'; } > "$T/alien.env"
    if lint_env "$T/alien.env"; then echo "[gw-verify][RED] T9 FAIL（SGLANG_DEFAULT_THINKING=1 未判红）"; rc=1
    else echo "[gw-verify][OK] T9 SGLANG_DEFAULT_THINKING=1 异键判红（#45614 触发面禁入）"; fi
    sed 's|^SGLANG_DEFAULT_THINKING=.*|SGLANG_DEFAULT_THINKING=0|' "$T/alien.env" > "$T/alien0.env"
    if lint_env "$T/alien0.env"; then echo "[gw-verify][RED] T9 FAIL（=0 假形异键未判红）"; rc=1
    else echo "[gw-verify][OK] T9 SGLANG_DEFAULT_THINKING=0 假形亦判红（异键=值无关一律禁入）"; fi
    # T10 主车道注入律（#45614）：INJECT_ENABLE_THINKING 必须=1——=0/缺键必红
    sed 's|^INJECT_ENABLE_THINKING=.*|INJECT_ENABLE_THINKING=0|' "$T/good.env" > "$T/noinj.env"
    if lint_env "$T/noinj.env"; then echo "[gw-verify][RED] T10 FAIL（主车道 INJECT=0 未判红）"; rc=1
    else echo "[gw-verify][OK] T10 主车道 INJECT_ENABLE_THINKING=0 判红（裸请求双键兜底缺省必须开）"; fi
    grep -v '^INJECT_ENABLE_THINKING=' "$T/good.env" > "$T/missinj.env"
    if lint_env "$T/missinj.env"; then echo "[gw-verify][RED] T10 FAIL（主车道 INJECT 缺键未判红）"; rc=1
    else echo "[gw-verify][OK] T10 主车道 INJECT_ENABLE_THINKING 缺键判红"; fi
    # T11 车道分形判别力：同一 =0 env——vl 车道（域检查 {0,1}）绿、主车道（必须=1）红
    if lint_env "$T/noinj.env" vl; then echo "[gw-verify][OK] T11 vl 车道 INJECT=0 域内绿（呈裁 C3 形；lane 分形工作）"
    else echo "[gw-verify][RED] T11 FAIL（vl 车道把 =0 误判红——lane 未分形）"; rc=1; fi
    rm -rf "$T"; exit "$rc" ;;
  *) echo "用法：$0 --offline <env 文件> [vl env 文件] | --live | --selfcheck" >&2; exit 2 ;;
esac
