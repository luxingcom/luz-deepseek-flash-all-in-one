"""replay_guard 单元测：check() 三分支 + install() 幂等 + features 门。
判别力自检：坏用例（bounded=True 且要 prompt logprob）必须红——守卫不红=没牙。"""
import sys, types
sys.path.insert(0, "/opt/dsv41/adapter")
import replay_guard as rg

class Obj:  # 请求对象桩
    def __init__(self, **kw): self.__dict__.update(kw)

# 1) bounded=False（我方现行态）：一切请求放行
for o in (Obj(return_logprob=True, logprob_start_len=0),
          Obj(return_hidden_states=True),
          Obj()):
    rg.check(o, [1]*100, bounded_replay=False)
print("T1 flag-off passthrough: OK")

# 2) bounded=True：三类必须 ValueError
def must_raise(o, tag):
    try: rg.check(o, [1]*100, bounded_replay=True)
    except ValueError: print(f"T2 {tag}: raises OK"); return
    raise SystemExit(f"T2 {tag}: FAILED to raise (guard toothless)")
must_raise(Obj(return_logprob=True, logprob_start_len=0), "prompt-logprob@0")
must_raise(Obj(return_logprob=True, logprob_start_len=99), "prompt-logprob@n-1")
must_raise(Obj(return_hidden_states=True), "full-hidden")
# 放行面：output-only logprob / start=None / start>=n / hidden='last'
for o in (Obj(return_logprob=False, logprob_start_len=0),
          Obj(return_logprob=True, logprob_start_len=None),
          Obj(return_logprob=True, logprob_start_len=100),
          Obj(return_logprob=True, logprob_start_len=-1),
          Obj(return_hidden_states="last")):
    rg.check(o, [1]*100, bounded_replay=True)
print("T3 output-only passthrough: OK")

# 3) install()：桩模块上打补丁、幂等、包装器走 features 门
mod = types.ModuleType("sglang.srt.managers.tokenizer_manager")
class TM:
    def _validate_one_request(self, obj, input_ids): return "orig"
mod.TokenizerManager = TM
class GRI(Obj):  # 类型名必须是 GenerateReqInput 才进 check()
    pass
GRI.__name__ = "GenerateReqInput"
class Exec:  # features 桩：flag off
    class features: enable_decoder_swa_bounded_replay = False
mod.get_exec = lambda: Exec()
rg.install(mod)
tm = TM()
assert tm._validate_one_request(GRI(return_logprob=True, logprob_start_len=0), [1]*50) == "orig"
print("T4 installed wrapper flag-off passthrough: OK")
Exec.features.enable_decoder_swa_bounded_replay = True
try:
    tm._validate_one_request(GRI(return_logprob=True, logprob_start_len=0), [1]*50)
    raise SystemExit("T5 FAILED: wrapper did not reject under flag-on")
except ValueError: print("T5 installed wrapper flag-on rejects: OK")
rg.install(mod)  # 幂等：不双包
print("T6 idempotent install: OK")
print("ALL-PASS")
