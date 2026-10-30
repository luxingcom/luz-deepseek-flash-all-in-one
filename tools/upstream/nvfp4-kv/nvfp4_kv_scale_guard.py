#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nvfp4_kv_scale_guard — nvfp4 KV cache 复用 fp8 标定 k/v_scale 的加载期校验守卫（host 侧规避件）。

上游缺陷（sgl-project/sglang issue #42369，2026-10 调研窗纳入）：
  `--kv-cache-dtype nvfp4` 时，引擎经 maybe_remap_kv_scale_name/load_weights 静默加载
  checkpoint 里 fp8 标定（kv_cache_scheme.num_bits=8，amax/448 几何）的逐层
  *.self_attn.{k,v}_scale 张量，当作 NVFP4 全局 scale（amax/6 几何）使用——约 75 倍
  失配，无任何校验与日志。症状为隐蔽的长上下文退化（needle 检索崩、答案复读），
  短 prompt/工具调用/启动日志全正常。上游修复（加载期 num_bits×运行时 dtype 校验+
  动态回退）未发布；本守卫在 host 侧代位：把「开门前先核 checkpoint 面与 runtime
  dtype 的几何一致性」变成可断言对象（fail-closed）。

判定矩阵（runtime --kv-cache-dtype × checkpoint 面）：
  ① runtime=nvfp4 + checkpoint 带 k/v_scale 张量且 scheme.num_bits≠4（含 scheme 缺失）
     → FAIL：即 issue 命中态，须先跑 nvfp4_strip_kv_scales.py 剥 scales 走动态路径，
       并过 nvfp4_needle_gate.py 验收门后再开门。
  ② runtime=nvfp4 + 带 k/v_scale 且 scheme.num_bits=4 → PASS：ModelOpt NVFP4-KV 正当
     标定形（issue 报告者明言 num_bits:4 导出件应保留加载其 scales），不误杀。
  ③ runtime=nvfp4 + 无 k/v_scale 且 scheme=null → PASS：动态 scale 路径
     （报告者生产验证形：剥后 needle d50/d500 = 4/4+4/4）。
  ④ runtime=nvfp4 + 无张量但 scheme.num_bits=8 → WARN：张量缺失故无错用发生，但
     scheme 声明与 nvfp4 运行时语义矛盾，建议置 null 消歧（不拦门）。
  ⑤ runtime 未启用/非 nvfp4（auto/fp8_e4m3/bf16/…）→ PASS：几何不命中（fp8 KV 与
     fp8 标定同几何=正当形）；守卫作为「未来开门」的前置断言面常备。
  fail-closed：runtime=nvfp4 但未给 --model-dir（无法核 checkpoint 面）→ rc=2；
  checkpoint/env 取证失败 → rc=2。

用法（产线正典面）：
  python3 tools/upstream/nvfp4-kv/nvfp4_kv_scale_guard.py            # 缺省=lint 正典四面+正典 checkpoint
  python3 tools/upstream/nvfp4-kv/nvfp4_kv_scale_guard.py --argv "$(tr '\\0' ' ' </proc/1/cmdline)"
  python3 tools/upstream/nvfp4-kv/nvfp4_kv_scale_guard.py --serve-file X --model-dir /data/models/M
  python3 tools/upstream/nvfp4-kv/nvfp4_kv_scale_guard.py --selfcheck  # 离线合成判据自检（G1-G7）

退出码：0=PASS/WARN；1=FAIL（issue 命中态/配置面自相矛盾）；2=取证失败（fail-closed）。
红线：只读取证（header/config/argv 文本），零写零 git，不触引擎与容器生命周期。
"""
import argparse
import glob
import json
import os
import re
import struct
import sys
import tempfile

ISSUE_URL = "https://github.com/sgl-project/sglang/issues/42369"
GUARD_VER = "nvfp4-kv-guard/1.0 (issue #42369 host-side guard)"

# 产线正典面（缺省 lint 对象；缺位的面记 INFO 不拦门——公开仓快照环境无 migrate-assets）。
DEFAULT_SERVE_FILES = [
    "~/migrate-assets/bin/r3-boot-arm.sh",
    "~/migrate-assets/prod/prod-profile.env",
    "~/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env",
    "~/dsv41-flash-dgxsparks/.env.tp4",
]
DEFAULT_MODEL_DIR = "/data/models/DeepSeek-V4.1-Flash-1017"

# KV scale 张量判定：issue 精确形=*.self_attn.{k,v}_scale（compressed-tensors 命名）；
# 广义形=任何 .k_scale/.v_scale 后缀张量（vLLM/SGLang 的 maybe_remap_kv_scale_name 族
# 认名面更宽，守卫按广义计数以免漏报；报告分两层呈现）。
RE_SCALE_EXACT = re.compile(r"(?:^|\.)self_attn\.(k_scale|v_scale)$")
RE_SCALE_BROAD = re.compile(r"(?:^|\.)(k_scale|v_scale)$")
RE_KV_FLAG = re.compile(r"--kv-cache-dtype")


def eprint(*a):
    print(*a, file=sys.stderr)


# ── safetensors header 只读解析（8B 小端长度 + JSON；不装第三方库） ──
def read_st_headers(model_dir):
    """返回 {filename: header_dict}；解析失败抛异常由调用方转 rc=2。"""
    out = {}
    for fp in sorted(glob.glob(os.path.join(model_dir, "*.safetensors"))):
        with open(fp, "rb") as f:
            raw_len = f.read(8)
            if len(raw_len) != 8:
                raise IOError("safetensors 头长度段不完整: %s" % fp)
            hlen = struct.unpack("<Q", raw_len)[0]
            if hlen <= 0 or hlen > 64 * 1024 * 1024:
                raise IOError("safetensors 头长度异常(%d): %s" % (hlen, fp))
            out[os.path.basename(fp)] = json.loads(f.read(hlen).decode("utf-8"))
    if not out:
        raise IOError("目录内无 *.safetensors: %s" % model_dir)
    return out


def scan_scales(headers):
    """返回 (exact_hits, broad_other)：精确形=self_attn.{k,v}_scale（issue 命中命名）；
    broad_other=其余 *.k_scale/.v_scale 后缀张量。判定用两者合计（总命中数）。"""
    exact, broad = [], []
    for fname, hdr in sorted(headers.items()):
        for name in hdr:
            if name == "__metadata__":
                continue
            if RE_SCALE_EXACT.search(name):
                exact.append("%s::%s" % (fname, name))
            elif RE_SCALE_BROAD.search(name):
                broad.append("%s::%s" % (fname, name))
    return exact, broad


def read_scheme(model_dir):
    """读 config.json 的 kv_cache_scheme（quantization_config 内优先，顶层次之）。
    返回 (found, scheme_value)；config 不可读抛异常。"""
    path = os.path.join(model_dir, "config.json")
    cfg = json.load(open(path, "r", encoding="utf-8"))
    quant = cfg.get("quantization_config") or {}
    if isinstance(quant, dict) and "kv_cache_scheme" in quant:
        return True, quant.get("kv_cache_scheme")
    if "kv_cache_scheme" in cfg:
        return True, cfg.get("kv_cache_scheme")
    return False, None


def scheme_num_bits(scheme):
    if isinstance(scheme, dict):
        nb = scheme.get("num_bits")
        if isinstance(nb, int):
            return nb
    return None


# ── runtime dtype 取证：argv（生效值优先）与静态面 lint ──
def tokens_from_text(text):
    """bash 数组/env 文件的行内 lint：剥 # 注释段后按空白分词（参数与值同行的正典制式）。"""
    toks = []
    for line in text.splitlines():
        body = line.split("#", 1)[0]
        toks.extend(body.split())
    return toks


def parse_dtype_from_tokens(tokens, src_label, findings):
    """在 token 流中找 --kv-cache-dtype（空格分隔与 = 连写两形）；记入 findings。"""
    val = None
    for i, t in enumerate(tokens):
        if not RE_KV_FLAG.search(t):
            continue
        if "=" in t:
            v = t.split("=", 1)[1]
        elif i + 1 < len(tokens):
            v = tokens[i + 1]
        else:
            findings.append(("FAIL", "[%s] %s 出现但无值（截断/残面）" % (src_label, t)))
            continue
        if val is not None and val != v:
            findings.append(("FAIL", "[%s] --kv-cache-dtype 多处出现且值不一（%s vs %s）=配置面自相矛盾"
                             % (src_label, val, v)))
        val = v
        findings.append(("INFO", "[%s] --kv-cache-dtype=%s" % (src_label, v)))
    return val


def lint_serve_files(serve_files, findings):
    """静态面 lint：返回 runtime dtype（多源以并集呈现，值冲突已在上层记 FAIL）。"""
    val = None
    seen_any = False
    for sf in serve_files:
        p = os.path.expanduser(sf)
        if not os.path.exists(p):
            findings.append(("INFO", "面缺位（不拦门）：%s" % sf))
            continue
        text = open(p, "r", encoding="utf-8", errors="replace").read()
        v = parse_dtype_from_tokens(tokens_from_text(text), os.path.basename(p), findings)
        seen_any = True
        if v is not None:
            val = v
    return val, seen_any


# ── 联合判定 ──
def judge(runtime, model_info, findings):
    """model_info=None 表示未核 checkpoint 面。返回 rc（0/1/2）。"""
    if runtime is None:
        findings.append(("PASS", "runtime 未启用 --kv-cache-dtype（引擎缺省 auto，KV cache 走 "
                                 "fp8/bf16 几何）——不命中 issue #42369 命中态。"))
        if model_info and (model_info["n_scales"] > 0 or model_info["scheme_found"]):
            findings.append(("INFO", "checkpoint 面带 KV scale/scheme 声明：未来若开 "
                                     "--kv-cache-dtype nvfp4，开门前先过本守卫（判据①须先剥 scales）。"))
        return 0
    if runtime == "nvfp4":
        if model_info is None:
            findings.append(("FATAL", "runtime=nvfp4 但未提供 --model-dir，checkpoint 面未核"
                                      "=无法判定（fail-closed，不得放行）。"))
            return 2
        nb = model_info["num_bits"]
        if model_info["n_scales"] > 0 and nb == 4:
            findings.append(("PASS", "runtime=nvfp4 且 scheme.num_bits=4：NVFP4-KV 正当标定形"
                                     "（ModelOpt 导出件保留加载其 scales），不命中缺陷。"))
            return 0
        if model_info["n_scales"] > 0:
            findings.append(("FAIL", "issue #42369 命中态：runtime=nvfp4 而 checkpoint 带 %d 个 "
                                     "k/v_scale 张量且 scheme.num_bits=%s（fp8 标定/未声明几何）——"
                                     "引擎将静默把它们当 NVFP4 全局 scale（约 75 倍失配），长上下文检索"
                                     "将隐蔽崩塌。先跑 nvfp4_strip_kv_scales.py 剥 scales 走动态路径，"
                                     "并过 nvfp4_needle_gate.py（d50/d500）验收门后再开门：%s"
                                     % (model_info["n_scales"], nb, ISSUE_URL)))
            return 1
        if model_info["scheme_found"] and nb not in (None, 4):
            findings.append(("WARN", "runtime=nvfp4，checkpoint 无 k/v_scale 张量（无错用发生），"
                                     "但 kv_cache_scheme.num_bits=%s 与 nvfp4 运行时语义矛盾——"
                                     "建议手术时一并置 null 消歧（不拦门）。" % nb))
            return 0
        findings.append(("PASS", "runtime=nvfp4 且 checkpoint 无 k/v_scale 张量、scheme=null/缺省："
                                 "动态 scale 路径（issue 报告者生产验证形，剥后 needle "
                                 "d50/d500=4/4+4/4）。"))
        return 0
    findings.append(("PASS", "runtime --kv-cache-dtype=%s 非 nvfp4：几何不命中 issue #42369"
                             "（fp8 KV 与 fp8 标定同几何为正当形）。" % runtime))
    return 0


def run_guard(args):
    findings = []
    runtime = None
    if args.argv is not None:
        runtime = parse_dtype_from_tokens(args.argv.split(), "--argv", findings)
    elif args.argv_file:
        raw = open(args.argv_file, "rb").read().replace(b"\x00", b" ")
        runtime = parse_dtype_from_tokens(raw.decode("utf-8", "replace").split(),
                                          os.path.basename(args.argv_file), findings)
    else:
        runtime, seen = lint_serve_files(args.serve_file or DEFAULT_SERVE_FILES, findings)
        if not seen and not args.model_dir:
            # 公开仓快照环境：既无生效值又无静态面——只跑 checkpoint 报告面。
            findings.append(("INFO", "本环境无正典静态面（公开仓快照）：runtime 面未取证，"
                                     "仅作 checkpoint 面报告。"))

    model_info = None
    if args.model_dir:
        model_dir = os.path.expanduser(args.model_dir)
        try:
            if not os.path.isdir(model_dir):
                raise IOError("目录不存在: %s" % model_dir)
            headers = read_st_headers(model_dir)
            exact, broad = scan_scales(headers)
            scheme_found, scheme = read_scheme(model_dir)
            nb = scheme_num_bits(scheme)
            n_scales = len(exact) + len(broad)
            model_info = {"n_exact": len(exact), "n_broad": len(broad), "n_scales": n_scales,
                          "scheme_found": scheme_found,
                          "scheme_value": scheme, "num_bits": nb,
                          "n_shards": len(headers)}
            findings.append(("INFO", "checkpoint=%s：%d 分片 header 亲读；k/v_scale 张量 "
                                     "精确形(self_attn.*)=%d、广义形=%d；kv_cache_scheme=%s。"
                                     % (model_dir, len(headers), len(exact), len(broad),
                                        json.dumps(scheme, ensure_ascii=False)
                                        if scheme_found else "缺省（无声明）")))
        except Exception as exc:
            findings.append(("FATAL", "checkpoint 面取证失败（fail-closed）：%s" % exc))
            return emit(findings, 2)

    rc = judge(runtime, model_info, findings)
    return emit(findings, rc)


def emit(findings, rc):
    for level, msg in findings:
        print("%-4s %s" % (level, msg))
    verdict = {0: "PASS（守卫绿）", 1: "FAIL（守卫红：issue #42369 命中态/配置面矛盾）",
               2: "FATAL（取证失败，fail-closed）"}[rc]
    print("== nvfp4_kv_scale_guard 判定：%s rc=%d ==" % (verdict, rc))
    return rc


# ── 离线自检（G1-G7：合成 safetensors+config 判据分支与负控制；不写仓内） ──
def _make_st(path, with_scales):
    import tempfile, shutil
    os.makedirs(path, exist_ok=True)
    tensors = {
        "model.layers.0.self_attn.q_proj.weight": ("F32", [4, 4], list(range(16))),
        "model.layers.0.self_attn.o_proj.weight": ("F32", [4, 4], list(range(16, 32))),
    }
    if with_scales:
        tensors["model.layers.0.self_attn.k_scale"] = ("BF16", [1], [1])
        tensors["model.layers.0.self_attn.v_scale"] = ("BF16", [1], [2])
    hdr, blob, off = {}, bytearray(), 0
    for name, (dt, shape, data) in tensors.items():
        raw = b"".join(struct.pack("<f", float(v)) for v in data)
        hdr[name] = {"dtype": dt, "shape": shape,
                     "data_offsets": [off, off + len(raw)]}
        blob += raw
        off += len(raw)
    hdr["__metadata__"] = {"format": "pt"}
    hj = json.dumps(hdr).encode("utf-8")
    pad = (8 - (len(hj) % 8)) % 8
    with open(os.path.join(path, "model-00001-of-00001.safetensors"), "wb") as f:
        f.write(struct.pack("<Q", len(hj) + pad) + hj + b" " * pad + bytes(blob))
    return hdr


def _make_cfg(path, scheme):
    cfg = {"architectures": ["X"], "quantization_config": {"quant_method": "fp8"}}
    if scheme is not ...:
        cfg["quantization_config"]["kv_cache_scheme"] = scheme
    with open(os.path.join(path, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def selfcheck():
    tmp = tempfile.mkdtemp(prefix="nvfp4-guard-selfcheck-")
    cases = []
    # 判据①：nvfp4 + fp8 标定（num_bits=8 + 张量）→ FAIL=1
    d = os.path.join(tmp, "c1"); _make_st(d, True); _make_cfg(d, {"num_bits": 8})
    cases.append(("G1 nvfp4+num_bits8+scales→FAIL", d, ["--model-dir", d],
                  "--kv-cache-dtype nvfp4 --model-path /m", 1))
    # 判据③：nvfp4 + 无张量 + scheme null → PASS=0
    d = os.path.join(tmp, "c3"); _make_st(d, False); _make_cfg(d, None)
    cases.append(("G3 nvfp4+剥离形(动态路径)→PASS", d, [],
                  "--kv-cache-dtype nvfp4", 0))
    # 判据②：nvfp4 + num_bits=4 + 张量 → PASS=0（正当标定形不误杀）
    d = os.path.join(tmp, "c2"); _make_st(d, True); _make_cfg(d, {"num_bits": 4})
    cases.append(("G2 nvfp4+num_bits4+scales→PASS", d, [],
                  "--kv-cache-dtype nvfp4", 0))
    # 判据⑤：runtime 未启用 + checkpoint 带标定 → PASS=0（附 INFO）
    d = os.path.join(tmp, "c5"); _make_st(d, True); _make_cfg(d, {"num_bits": 8})
    cases.append(("G5 无dtype+fp8标定面→PASS", d, [], "", 0))
    # 判据④：nvfp4 + 无张量 + scheme num_bits=8 → WARN=0
    d = os.path.join(tmp, "c4"); _make_st(d, False); _make_cfg(d, {"num_bits": 8})
    cases.append(("G4 nvfp4+无张量+scheme8→WARN(0)", d, [],
                  "--kv-cache-dtype nvfp4", 0))
    # fail-closed：nvfp4 但未核 checkpoint → rc=2
    cases.append(("G6 nvfp4+未核checkpoint→FATAL(2)", None, ["--model-dir", "none"],
                  "--kv-cache-dtype nvfp4", 2))
    # = 连写形解析
    d = os.path.join(tmp, "c7"); _make_st(d, True); _make_cfg(d, {"num_bits": 8})
    cases.append(("G7 连写形--kv-cache-dtype=nvfp4→FAIL", d, [],
                  "--kv-cache-dtype=nvfp4 --context-length 600000", 1))

    n_pass = 0
    for label, mdir, extra, argv, want in cases:
        ap = build_parser()
        a = ap.parse_args(extra + ["--argv", argv] if argv else extra)
        if mdir and "--model-dir" not in extra:
            a.model_dir = mdir
        rc = run_guard(a)
        ok = (rc == want)
        n_pass += ok
        print("%s %s（期望 rc=%d 实测 rc=%d）" % ("PASS" if ok else "FAIL", label, want, rc))

    # 判别力负控制：G1 若去掉 runtime nvfp4（回到 fp8 几何）必须转绿——证明红灯
    # 确由「nvfp4×fp8 标定」组合触发而非 checkpoint 面本身误报。
    ap = build_parser()
    a = ap.parse_args(["--argv", "--kv-cache-dtype fp8_e4m3", "--model-dir",
                       os.path.join(tmp, "c1")])
    rc = run_guard(a)
    ok = (rc == 0)
    n_pass += ok
    print("%s 负控制 fp8_e4m3×同面→PASS（判别力证明，rc=%d）" % ("PASS" if ok else "FAIL", rc))

    total = len(cases) + 1
    print("== selfcheck 结束：%d/%d ==" % (n_pass, total))
    return 0 if n_pass == total else 1


def build_parser():
    ap = argparse.ArgumentParser(description="nvfp4 KV cache scale 守卫（issue #42369 host 侧代位校验）")
    ap.add_argument("--argv", help="serve 进程 argv 字符串（生效值优先取证面）")
    ap.add_argument("--argv-file", help="NUL/空白分隔 argv 落盘文件（/proc/PID/cmdline 形）")
    ap.add_argument("--serve-file", action="append",
                    help="静态 lint 面（可多次；缺省=产线正典四面）")
    ap.add_argument("--model-dir", default=DEFAULT_MODEL_DIR,
                    help="checkpoint 目录（默认 %s；传 none 跳过 checkpoint 面）" % DEFAULT_MODEL_DIR)
    ap.add_argument("--selfcheck", action="store_true", help="离线判据自检（合成件，不发包不写仓）")
    return ap


def main():
    args = build_parser().parse_args()
    if args.selfcheck:
        return selfcheck()
    if args.model_dir and args.model_dir.lower() == "none":
        args.model_dir = None
    return run_guard(args)


if __name__ == "__main__":
    sys.exit(main())
