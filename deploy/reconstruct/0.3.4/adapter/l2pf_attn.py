"""EP1g-#3 (KNAPCIO-RECON 9817936): L2PF 武装件 -- 注意力 AR 面（第二缝）。

现状（对账结论）：移植件 adapter/l2_prefetch.py（knapcio @ 9df6ffe 血统，头部有
sha256=996dc24ea31c6aa3 血统标记，故本件不改它、另立文件）只盖 MoE AR 半边：
install_collectives 挂 sglang.srt.distributed.communication_op 与
sglang.srt.layers.communicator 两命名空间的 tensor_model_parallel_all_reduce /
attention_ / moe_ 变体与 all_gather。而 main 注意力 AR 不走这两处：
    sglang/srt/layers/dp_attention.py:1142
        def attn_tp_all_reduce(input): return get_parallel().attn_tp_group.all_reduce(input)
    -> GroupCoordinator.all_reduce（parallel_state.py:666）
调用点：models/deepseek_v4.py:2531/2565（注意力输出 o 的 TP 归约；:88 from-import
绑定名字）、layers/vocab_parallel_embedding.py:586、各 MHA 模型。该窗口对 plan
不可见 -- 按移植件自身不变式，未挂点只是漏窗，从不出错；但注意力 AR 后紧接的
权重读（首当其冲是 bf16 router，install_router 记录 tiny_gemm_bf16 正为此；其后
是下游 MXFP8 稠密层）从未被预取。

本缝做法（wrap all_reduce 的选型见 QUALIFY.md）：不动 GroupCoordinator.all_reduce
类方法（那会把 DP/EP/TP 全组混进一个 per-forward 编号，且与构造期捕获的非绑定
方法竞态），而是在 sglang.srt.layers.dp_attention 模块 exec 时包
attn_tp_all_reduce，与移植件 NCCL 钩同一形状：发射前调
l2_prefetch._before_collective("ar", None)。同一学习/编号机制自动生效：eager 热身
按程序序给所有已挂 collective 编号，记录器把每段权重记在它前面最后一个 collective
名下，capture 回放同一 Python 序列 ⇒ 预取成为图分支。双计数不可能：
dp_attention.attn_tp_all_reduce 与 communication_op 的 AR 入口都是
GroupCoordinator.all_reduce 之上的叶子包装，互不嵌套（docker 实读核验，
engine-evidence/）。

挂点必须在 exec 时装（sitecustomize 的 EngramLoader），不是首次调用前补装：
deepseek_v4.py:88 的 from sglang.srt.layers.dp_attention import attn_tp_all_reduce
在本模块 exec 完即绑定函数对象，之后改模块属性追不上已绑定的消费者。finder
白名单加 'sglang.srt.layers.dp_attention' 是 load-bearing 的。

武装键（fail-safe，与家族纪律一致；两者都开才装钩）：
  DSV41_L2_PREFETCH=1  主门（框架：记录器/plan/内核库，即移植件原有键）
  DSV41_L2PF_ATTN=1    本缝独有；不设 = 现状逐字节不变（只盖 MoE 面）
预取哪块权重：不硬编码 -- 学到的"注意力 AR 之后将被读的下一段权重"，本栈即
router（tiny_gemm_bf16）起、按消耗序的后继 MXFP8 段，同一
DSV41_L2_PREFETCH_MB 预算。过期 plan 只浪费带宽（移植件不变式）。

自检：python3 test_l2pf_attn.py（CPU-only，宿主无 torch 时以最小桩代）。
"""
import logging
import os

import l2_prefetch
from l2_prefetch import _before_collective, _lib

logger = logging.getLogger(__name__)

_MARKER = "_dsv41_l2pf_attn"


def attn_enabled():
    """与 l2_prefetch.enabled() 同法的 fail-safe：只有显式真 token 才武装。"""
    return os.environ.get("DSV41_L2PF_ATTN", "0").strip() in ("1", "on", "true")


def install_dp_attention(module):
    """包 dp_attention.attn_tp_all_reduce：发射前预取下一段权重进 L2。

    双门都开才动文件；否则原样返回（缺省行为 = 现状，向后兼容）。幂等：包装带
    _dsv41_l2pf_attn 标记，重装不叠包。装上后调 _lib() 逼错误在靴时暴露而非
    首个 decode 步（与 install_collectives 同纪律）。
    """
    if not l2_prefetch.enabled() or not attn_enabled():
        return
    patched = 0
    original = getattr(module, "attn_tp_all_reduce", None)
    if original is not None and not getattr(original, _MARKER, False):

        def attn_tp_all_reduce(input_, _original=original):
            _before_collective("ar", None)
            return _original(input_)

        attn_tp_all_reduce.__name__ = "attn_tp_all_reduce"
        setattr(attn_tp_all_reduce, _MARKER, True)
        module.attn_tp_all_reduce = attn_tp_all_reduce
        patched += 1
    if patched:
        _lib()
    logger.warning("DSV41_L2PF_ATTN: %d attention-AR entry point(s) prefetch the next "
                   "weights into L2 (dp_attention.attn_tp_all_reduce)", patched)
