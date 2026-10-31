"""R1 Selection 落盘钩（VERIFICATION.md 判别①的引擎级扩展，设计在案未实现→本件补齐）。

用途：认证火/判别靴上，键开/键关同批同种子各跑一遍 decode，把消费面写回的
``Selection.page_indices / raw_indices`` 逐层落盘（.pt），供键面 A/B 逐元素比对——
「gather 消费面 vs dense 消费面写回逐元素相等」的引擎级证据形态。

纪律：
- 键 ``DSV41_SPARSE_LOCAL_DUMP``（路径；键缺省/空 = 关，零副作用）。
- **量具 fail-closed**：目录不可建/不可写 → 一次性横幅后自禁（产径绝不被量具拖死；
  seam_mount 调用点对 dump 异常整体吞并，此处只需自禁不抛）。
- 上界：``DSV41_SPARSE_LOCAL_DUMP_MAX``（缺省 64 个文件/进程）——防长跑把盘写爆
  （9/30 事故教义：量具自身不许成为风暴源）。文件名 ``<face>-L<layer>-<seq>.pt``，
  内容 {page_indices, raw_indices, layer_id, face, torch_version, note}。
- 落盘在写回合同完成后进行（dumps 的是消费面最终 Selection，不是中间 logits）。
"""

from __future__ import annotations

import os

DUMP_ENV = "DSV41_SPARSE_LOCAL_DUMP"
MAX_ENV = "DSV41_SPARSE_LOCAL_DUMP_MAX"
DEFAULT_MAX = 64

_state = {"dir": None, "max": DEFAULT_MAX, "count": 0, "disabled": False}


def _configure() -> None:
    if _state["dir"] is not None or _state["disabled"]:
        return
    raw = os.environ.get(DUMP_ENV, "").strip()
    if not raw:
        _state["disabled"] = True   # 键关：maybe_dump 每调用一次布尔判断即返
        return
    try:
        os.makedirs(raw, exist_ok=True)
        probe = os.path.join(raw, ".r1_dump_probe")
        with open(probe, "w") as fh:
            fh.write("probe")
        os.remove(probe)
    except OSError as exc:
        print(f"[sparse_local_dump] REFUSED -> dumping disabled. why: {raw!r} "
              f"not writable ({exc})", flush=True)
        _state["disabled"] = True
        return
    try:
        mx = int(os.environ.get(MAX_ENV, "").strip() or DEFAULT_MAX)
    except ValueError:
        mx = DEFAULT_MAX
    _state["dir"] = raw
    _state["max"] = mx
    print(f"[sparse_local_dump] selection dump ARMED dir={raw} max_files={mx}",
          flush=True)


def enabled() -> bool:
    _configure()
    return _state["dir"] is not None and not _state["disabled"]


def maybe_dump(face: str, layer_id: int, page=None, raw=None) -> None:
    """seam 消费面写回完成后的落盘点（键关=一次布尔判断；任何异常自吞）。

    520d6d0 新合同：消费面无 Selection out 参——直接收张量参（page/raw；
    decode 面 raw=None=新合同 decode 无 raw，prefill 面 raw=inputs.out_raw_indices）。
    """
    try:
        if not enabled():
            return
        if _state["count"] >= _state["max"]:
            if _state["count"] == _state["max"]:  # 恰超界那一次横幅，之后静默
                print(f"[sparse_local_dump] cap {_state['max']} reached; "
                      f"further dumps suppressed", flush=True)
                _state["count"] += 1
            return
        import torch

        seq = _state["count"]
        _state["count"] += 1
        path = os.path.join(_state["dir"], f"{face}-L{layer_id}-{seq:05d}.pt")
        payload = {
            "face": face,
            "layer_id": layer_id,
            "page_indices": (None if page is None else
                             page.detach().to(torch.int32).cpu().clone()),
            "raw_indices": (None if raw is None else
                            raw.detach().to(torch.int32).cpu().clone()),
            "note": "R1 gather consume face final outputs (post write contract; "
                    "tensor args per 520d6d0 no-Selection contract)",
        }
        torch.save(payload, path)
    except Exception as exc:  # 量具面失败不扰产径
        print(f"[sparse_local_dump] dump failed ({type(exc).__name__}: {exc}); "
              f"continuing", flush=True)


def reset_for_tests() -> None:
    """测试面：重置模块态（生产零调用）。"""
    _state.update(dir=None, max=DEFAULT_MAX, count=0, disabled=False)


def summary() -> str:
    _configure()
    if _state["disabled"] or _state["dir"] is None:
        return f"dump={DUMP_ENV}=(off)"
    return (f"dump={_state['dir']} files={_state['count']}/{_state['max']}")
