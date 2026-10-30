#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nvfp4_strip_kv_scales — NVFP4 checkpoint「剥 KV scales」手术件（issue #42369 host 侧规避正法）。

缺陷与修法（sgl-project/sglang issue #42369，报告者生产验证）：
  `--kv-cache-dtype nvfp4` 时引擎静默加载 checkpoint 里 fp8 标定（amax/448 几何）的
  *.self_attn.{k,v}_scale 张量当 NVFP4 全局 scale（amax/6 几何）=约 75 倍失配，长上下文
  检索隐蔽崩塌且零日志。上游修复未发布；正法=对 checkpoint 做剥 scales 手术：
    ① 从 model*.safetensors 删除 *.self_attn.{k,v}_scale 张量（缺省并剥一切
       *.k_scale/.v_scale 后缀张量，--exact-only 收窄回 issue 精确形）并重写 header
       offsets（其余张量数据字节级原样保留，仅紧凑化重排）；
    ② config.json 的 quantization_config.kv_cache_scheme 置 null；
    ③ 术后引擎走动态 scale 路径（报告者实测：剥前 needle d50/d500=1/4+0/4，
       剥后 4/4+4/4；185K prefill ~176s、decode ~25 tok/s 生产在役）。
  上线验收门=nvfp4_needle_gate.py（d50/d500 两档各 4 针须全中）；升级关注=上游把
  「加载期 num_bits×运行时 dtype 校验+不匹配回落动态」发布后，本手术对新 checkpoint
  退役（届时守卫判据②/③外的形态由上游拒载）。

安全制式：
  缺省 dry-run（零写盘）；--apply 才动盘。写盘走「临时文件+fsync+原子 rename」；
  原件 mv 为 <name>.bak-pre-nvfp4strip 字节保真备份（--no-bak 关，不建议）；
  apply 完成后自动跑逐张量字节校验（新旧文件每张量数据段 md5 逐一相等、scale 键零
  残留、张量数=原数-剥离数），校验不过即报红；手术全程零 git、零引擎/容器动作。
  磁盘预算：apply 前核 statvfs 可写空间 > 受影响分片总尺寸，不足拒做。

用法：
  python3 nvfp4_strip_kv_scales.py --model-dir /data/models/M            # dry-run 全报告
  python3 nvfp4_strip_kv_scales.py --model-dir /data/models/M --apply    # 执行手术
  python3 nvfp4_strip_kv_scales.py --selfcheck                           # 合成件离线自检

退出码：0=成功（dry-run 报告完成/apply+校验全绿/无可剥项）；1=校验 FAIL；2=用法或取证失败。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import time

ISSUE_URL = "https://github.com/sgl-project/sglang/issues/42369"
TOOL_VER = "nvfp4-strip-kv-scales/1.0"
RE_EXACT = re.compile(r"(?:^|\.)self_attn\.(k_scale|v_scale)$")
RE_BROAD = re.compile(r"(?:^|\.)(k_scale|v_scale)$")
BAK_SUFFIX = ".bak-pre-nvfp4strip"


def md5_file(path, beg=None, end=None):
    h = hashlib.md5()
    with open(path, "rb") as f:
        if beg is not None:
            f.seek(beg)
            remaining = end - beg
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                h.update(chunk)
                remaining -= len(chunk)
        else:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def read_header(fp):
    """返回 (header_dict, header_len)。损坏即抛异常（fail-closed）。"""
    with open(fp, "rb") as f:
        raw = f.read(8)
        if len(raw) != 8:
            raise IOError("头长度段不完整: %s" % fp)
        hlen = struct.unpack("<Q", raw)[0]
        if hlen <= 0 or hlen > 64 * 1024 * 1024:
            raise IOError("头长度异常(%d): %s" % (hlen, fp))
        return json.loads(f.read(hlen).decode("utf-8")), hlen


def plan_shard(fp, exact_only):
    """对单分片做手术计划：返回 (header, keep_names, strip_names, data_begin) 或
    （无张量可剥时）None 冲突信息。data_begin=8+hlen+pad（数据区起点，绝对偏移）。"""
    hdr, hlen = read_header(fp)
    data_begin = 8 + hlen
    data_begin += (8 - (data_begin % 8)) % 8  # safetensors 8 字节对齐填充
    matcher = RE_EXACT if exact_only else RE_BROAD
    keep, strip = [], []
    for name in hdr:
        if name == "__metadata__":
            keep.append(name)
            continue
        (strip if matcher.search(name) else keep).append(name)
    return hdr, keep, strip, data_begin


def rewrite_shard(fp, keep, strip, hdr, data_begin):
    """写新分片：<fp>.stripped.tmp：新 header（仅保留张量，__metadata__ 原位原样）+
    紧凑数据区（每张量字节自原文件原段复制）。返回 (new_path, new_header)。"""
    new_hdr = {}
    blob = bytearray()
    off = 0
    with open(fp, "rb") as src:
        for name in keep:
            if name == "__metadata__":
                new_hdr[name] = hdr[name]
                continue
            meta = dict(hdr[name])
            beg = data_begin + meta["data_offsets"][0]
            end = data_begin + meta["data_offsets"][1]
            src.seek(beg)
            raw = src.read(end - beg)
            if len(raw) != end - beg:
                raise IOError("张量数据段读短: %s %s" % (fp, name))
            meta["data_offsets"] = [off, off + len(raw)]
            new_hdr[name] = meta
            blob += raw
            off += len(raw)
    hj = json.dumps(new_hdr, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pad = (8 - (len(hj) % 8)) % 8
    new_path = fp + ".stripped.tmp"
    with open(new_path, "wb") as out:
        out.write(struct.pack("<Q", len(hj) + pad))
        out.write(hj)
        out.write(b" " * pad)
        out.write(blob)
        out.flush()
        os.fsync(out.fileno())
    return new_path, new_hdr


def verify_shard(orig_fp, orig_hdr, orig_data_begin, new_fp, strip_names):
    """术后校验：新分片可解析、strip 键零残留、保留张量逐张量 md5 与原段相等、
    张量数=原数-剥离数。返回问题列表（空=全绿）。"""
    problems = []
    new_hdr, new_hlen = read_header(new_fp)
    new_data_begin = 8 + new_hlen
    new_data_begin += (8 - (new_data_begin % 8)) % 8
    orig_names = [n for n in orig_hdr if n != "__metadata__"]
    new_names = [n for n in new_hdr if n != "__metadata__"]
    if len(new_names) != len(orig_names) - len(strip_names):
        problems.append("张量数不符：原 %d - 剥 %d ≠ 新 %d"
                        % (len(orig_names), len(strip_names), len(new_names)))
    for s in strip_names:
        if s in new_hdr:
            problems.append("剥离键残留：%s" % s)
    for name in new_names:
        if name not in orig_hdr:
            problems.append("新文件出现未知张量：%s" % name)
            continue
        om, nm = orig_hdr[name], new_hdr[name]
        if om["dtype"] != nm["dtype"] or om["shape"] != nm["shape"]:
            problems.append("张量元数据漂移：%s" % name)
            continue
        o_md5 = md5_file(orig_fp, orig_data_begin + om["data_offsets"][0],
                         orig_data_begin + om["data_offsets"][1])
        n_md5 = md5_file(new_fp, new_data_begin + nm["data_offsets"][0],
                         new_data_begin + nm["data_offsets"][1])
        if o_md5 != n_md5:
            problems.append("张量字节漂移：%s（%s≠%s）" % (name, o_md5, n_md5))
    return problems


def patch_config(model_dir, dry):
    """config.json 的 quantization_config.kv_cache_scheme 置 null（存在且非 null 时）。
    返回 (changed, before_md5, after_md5_or_None, note)。"""
    path = os.path.join(model_dir, "config.json")
    before = md5_file(path)
    cfg = json.load(open(path, "r", encoding="utf-8"))
    quant = cfg.get("quantization_config")
    target = None
    if isinstance(quant, dict) and quant.get("kv_cache_scheme") is not None:
        target = "quantization_config.kv_cache_scheme"
    elif cfg.get("kv_cache_scheme") is not None:
        target = "kv_cache_scheme"
    if target is None:
        return False, before, None, "kv_cache_scheme 本就为 null/缺省，无需置 null"
    if dry:
        return True, before, None, "dry-run：将把 %s 置 null（原值=%s）" % (
            target, json.dumps(cfg["quantization_config"].get("kv_cache_scheme")
                               if target.startswith("quant") else cfg.get("kv_cache_scheme"),
                               ensure_ascii=False))
    if target.startswith("quant"):
        cfg["quantization_config"]["kv_cache_scheme"] = None
    else:
        cfg["kv_cache_scheme"] = None
    tmp = path + ".stripped.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return True, before, md5_file(path), "已置 null：%s" % target


def run(args):
    model_dir = os.path.expanduser(args.model_dir)
    if not os.path.isdir(model_dir):
        print("FATAL 目录不存在：%s" % model_dir)
        return 2
    shards = sorted(glob.glob(os.path.join(model_dir, "*.safetensors")))
    if not shards:
        print("FATAL 目录内无 *.safetensors：%s" % model_dir)
        return 2
    if not os.path.exists(os.path.join(model_dir, "config.json")):
        print("FATAL 缺 config.json：%s" % model_dir)
        return 2

    plans, total_strip, total_bytes = [], 0, 0
    for fp in shards:
        try:
            hdr, keep, strip, data_begin = plan_shard(fp, args.exact_only)
        except Exception as exc:
            print("FATAL 分片 header 取证失败（fail-closed）：%s：%s" % (fp, exc))
            return 2
        if strip:
            strip_bytes = sum(hdr[s]["data_offsets"][1] - hdr[s]["data_offsets"][0] for s in strip)
            total_strip += len(strip)
            total_bytes += strip_bytes
            plans.append((fp, hdr, keep, strip, data_begin, strip_bytes))
    print("[plan] 分片 %d 件亲读；可剥 k/v_scale 张量 %d 个（%s形），涉分片 %d 件，"
          "剥离数据共 %d 字节；其余张量数据字节级原样保留（仅 offsets 重排）。"
          % (len(shards), total_strip, "issue 精确" if args.exact_only else "广义",
             len(plans), total_bytes))
    for fp, hdr, keep, strip, data_begin, sb in plans:
        print("[plan]   %s：剥 %s（%d 字节）" % (
            os.path.basename(fp),
            "、".join(".".join(s.split(".")[-2:]) for s in strip), sb))

    # 探测恒 dry（零写）：apply 模式下 config 真写延后到分片手术全绿之后（避免半手术态）。
    cfg_changed, cfg_before, cfg_after, cfg_note = patch_config(model_dir, dry=True)
    print("[cfg ] config.json：%s（before md5=%s%s）" % (
        cfg_note, cfg_before,
        " after md5=%s" % cfg_after if cfg_after else ""))

    if not plans and not cfg_changed:
        print("== 手术无需执行（0 张量可剥且 scheme 已 null）==")
        return 0
    if not args.apply:
        print("== dry-run 完成（未写盘）。确认后加 --apply 执行 ==")
        return 0

    # ── apply：磁盘预算 → 逐分片手术 → 原子换名 → 自动校验 ──
    need_bytes = sum(os.path.getsize(fp) for fp, *_ in plans)
    st = os.statvfs(model_dir)
    free = st.f_bavail * st.f_frsize
    if free < need_bytes * 1.05 + (1 << 30):
        print("FATAL 磁盘预算不足：需 ~%d 字节（受影响分片总量+5%%+1GiB 余量），"
              "可用 %d 字节——拒做（可用 --exact-only 收窄或先扩容）。" % (need_bytes, free))
        return 2

    manifest = {"tool": TOOL_VER, "issue": ISSUE_URL, "applied_at_utc": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model_dir": model_dir,
        "exact_only": args.exact_only, "shards": [], "problems": []}
    for fp, hdr, keep, strip, data_begin, sb in plans:
        orig_size = os.path.getsize(fp)
        orig_md5 = md5_file(fp)
        new_path, _ = rewrite_shard(fp, keep, strip, hdr, data_begin)
        problems = verify_shard(fp, hdr, data_begin, new_path, strip)
        if problems:
            os.unlink(new_path)
            manifest["problems"] += ["%s: %s" % (os.path.basename(fp), p) for p in problems]
            break
        bak = fp + BAK_SUFFIX
        if os.path.exists(bak):
            os.unlink(new_path)
            manifest["problems"].append("%s: 备份位已存在（%s），拒覆盖" % (os.path.basename(fp), bak))
            break
        os.rename(fp, bak)          # 原件字节保真留底
        os.rename(new_path, fp)     # 原子换名
        manifest["shards"].append({
            "file": os.path.basename(fp), "stripped": strip, "n_tensor_before": len(hdr) - 1,
            "n_tensor_after": len(keep) - (1 if "__metadata__" in keep else 0),
            "bytes_before": orig_size, "bytes_after": os.path.getsize(fp),
            "md5_before": orig_md5, "md5_after": md5_file(fp),
            "bak": os.path.basename(bak), "bak_md5": orig_md5})
        print("[apply] %s：剥 %d 张量，%d→%d 字节，校验绿（逐张量 md5 相等、零残留）；"
              "原件留底 %s" % (os.path.basename(fp), len(strip), orig_size,
                              os.path.getsize(fp), os.path.basename(bak)))

    cfg_changed, cfg_before, cfg_after, cfg_note = patch_config(model_dir, dry=False)
    manifest["config"] = {"changed": cfg_changed, "before_md5": cfg_before,
                          "after_md5": cfg_after, "note": cfg_note}
    sidecar = os.path.join(model_dir, "nvfp4-strip-manifest-%s.json"
                           % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    if manifest["problems"]:
        print("FATAL 术后校验发现问题（已中止受影响面，manifest 在档）：%s"
              % "; ".join(manifest["problems"]))
        print("== 手术 FAIL：恢复=从 %s* 备份回拷原分片 ==" % BAK_SUFFIX)
        return 1
    print("[apply] config.json：%s" % cfg_note)
    print("[apply] 手术台账：%s" % sidecar)
    print("== 手术完成：剥离 %d 张量；术后须过 nvfp4_kv_scale_guard.py（判据③绿）与 "
          "nvfp4_needle_gate.py（d50/d500 验收门）再开门 ==" % total_strip)
    return 0


# ── 离线自检：合成 2 分片+config → dry-run → apply → 校验 → 复扫零残留 ──
def _mk_shard(path, idx, n_layers=2):
    tensors = {}
    for L in range(n_layers):
        tensors["model.layers.%d.self_attn.q_proj.weight" % L] = ("F32", [2, 2], [float(L)] * 4)
        tensors["model.layers.%d.self_attn.k_scale" % L] = ("BF16", [1], [1.0])
        tensors["model.layers.%d.self_attn.v_scale" % L] = ("BF16", [1], [2.0])
    hdr, blob, off = {"__metadata__": {"format": "pt"}}, bytearray(), 0
    for name, (dt, shape, data) in tensors.items():
        raw = b"".join(struct.pack("<f", v) for v in data)
        hdr[name] = {"dtype": dt, "shape": shape, "data_offsets": [off, off + len(raw)]}
        blob += raw
        off += len(raw)
    hj = json.dumps(hdr, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pad = (8 - (len(hj) % 8)) % 8
    fp = os.path.join(path, "model-%05d-of-00002.safetensors" % idx)
    with open(fp, "wb") as f:
        f.write(struct.pack("<Q", len(hj) + pad) + hj + b" " * pad + bytes(blob))
    return fp


def selfcheck():
    tmp = tempfile.mkdtemp(prefix="nvfp4-strip-selfcheck-")
    d = os.path.join(tmp, "ckpt")
    os.makedirs(d)
    f1, f2 = _mk_shard(d, 1), _mk_shard(d, 2)
    json.dump({"architectures": ["X"], "quantization_config": {
        "quant_method": "compressed-tensors",
        "kv_cache_scheme": {"num_bits": 8}}},
        open(os.path.join(d, "config.json"), "w", encoding="utf-8"), indent=2)
    ap = build_parser()
    n_pass = 0
    total = 6

    # S1 dry-run：计划面=4 张量、2 分片、scheme 将置 null，且零写盘
    rc = run(ap.parse_args(["--model-dir", d]))
    dry_ok = (rc == 0) and os.path.getsize(f1) > 0 and not glob.glob(os.path.join(d, "*.tmp"))
    n_pass += dry_ok
    print("%s S1 dry-run 计划面正确且零写盘（rc=%d）" % ("PASS" if dry_ok else "FAIL", rc))

    # S2 apply：术后分片零 scale 残留、.bak 字节保真、逐张量校验内建绿
    before = {f1: md5_file(f1), f2: md5_file(f2)}
    rc = run(ap.parse_args(["--model-dir", d, "--apply"]))
    hdr1, _ = read_header(f1)
    scales_left = [n for n in hdr1 if n != "__metadata__" and RE_BROAD.search(n)]
    bak_ok = (os.path.exists(f1 + BAK_SUFFIX) and md5_file(f1 + BAK_SUFFIX) == before[f1]
              and os.path.exists(f2 + BAK_SUFFIX) and md5_file(f2 + BAK_SUFFIX) == before[f2])
    apply_ok = (rc == 0) and not scales_left and bak_ok
    n_pass += apply_ok
    print("%s S2 apply 剥离+备份字节保真+零残留（rc=%d，残留=%s，bak 保真=%s）"
          % ("PASS" if apply_ok else "FAIL", rc, scales_left, bak_ok))

    # S3 config 置 null 落盘
    cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
    cfg_ok = cfg["quantization_config"]["kv_cache_scheme"] is None
    n_pass += cfg_ok
    print("%s S3 config kv_cache_scheme 已置 null" % ("PASS" if cfg_ok else "FAIL"))

    # S4 保留张量字节校验（独立复算，不依赖工具内建校验）：新旧每张量 md5 相等
    old_hdr, _ = read_header(f1 + BAK_SUFFIX)
    raw_len = struct.unpack("<Q", open(f1 + BAK_SUFFIX, "rb").read(8))[0]
    old_data_begin = 8 + raw_len + (8 - ((8 + raw_len) % 8)) % 8
    all_eq = True
    for name, meta in old_hdr.items():
        if name == "__metadata__" or RE_BROAD.search(name):
            continue
        new_hdr, new_hlen = read_header(f1)
        new_data_begin = 8 + new_hlen + (8 - ((8 + new_hlen) % 8)) % 8
        a = md5_file(f1 + BAK_SUFFIX, old_data_begin + meta["data_offsets"][0],
                     old_data_begin + meta["data_offsets"][1])
        b = md5_file(f1, new_data_begin + new_hdr[name]["data_offsets"][0],
                     new_data_begin + new_hdr[name]["data_offsets"][1])
        all_eq = all_eq and (a == b)
    n_pass += all_eq
    print("%s S4 保留张量逐张量字节相等（独立复算）" % ("PASS" if all_eq else "FAIL"))

    # S5 复扫：dry-run 应报 0 可剥（幂等）
    rc = run(ap.parse_args(["--model-dir", d]))
    idem_ok = (rc == 0) and not glob.glob(os.path.join(d, "*.stripped.tmp"))
    n_pass += idem_ok
    print("%s S5 复扫幂等（0 可剥，rc=%d）" % ("PASS" if idem_ok else "FAIL", rc))

    # S6 台账在档
    man = glob.glob(os.path.join(d, "nvfp4-strip-manifest-*.json"))
    man_ok = bool(len(man) == 1 and json.load(open(man[0]))["shards"])
    n_pass += man_ok
    print("%s S6 手术台账在档（%s）" % ("PASS" if man_ok else "FAIL", man))

    print("== selfcheck 结束：%d/%d ==" % (n_pass, total))
    return 0 if n_pass == total else 1


def build_parser():
    ap = argparse.ArgumentParser(description="NVFP4 checkpoint 剥 KV scales 手术件（issue #42369）")
    ap.add_argument("--model-dir",
                    help="checkpoint 目录（--selfcheck 外必填）")
    ap.add_argument("--apply", action="store_true", help="执行写盘手术（缺省 dry-run 零写）")
    ap.add_argument("--exact-only", action="store_true",
                    help="只剥 *.self_attn.{k,v}_scale（issue 精确形）；缺省剥一切 *.k_scale/.v_scale 后缀")
    ap.add_argument("--selfcheck", action="store_true", help="合成件离线自检（不触产线目录）")
    return ap


def main():
    args = build_parser().parse_args()
    if args.selfcheck:
        return selfcheck()
    if not args.model_dir:
        ap = build_parser()
        ap.error("--selfcheck 外必须给 --model-dir")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
