"""Draft proposal temperature. Gated on DSV41_DRAFT_TAU (unset or 1 = off).

Multiplies the per-request temperature that the folded DSpark draft sampler uses (sampled requests
only; greedy rows stay argmax). The same tensor feeds the in-graph sampling of the draft tokens and
the draft probabilities of the rejection sampler (`dspark_draft` takes `draft_sampler.temperatures`
into the draft block, `accept_draft_tokens` softmaxes the corrected logits with it), so proposal and
acceptance always see the same q. Speculative sampling is exact for any q: the output distribution
does not change, only acceptance does.

Measured offline on held-out captured traffic at the model card's T=1 / top_p=0.95, with a draft
forward whose per-position acceptance matches the engine within 0.016: 0.8 raises accepted tokens
per step 3.242 -> 3.280 (+1.2 %); 0.7-0.8 is the optimum, 0.5 already gives some back.
Requires SGLANG_DSPARK_FOLDED_SAMPLING=2 (the folded sampler), which production sets.
"""
import os

TAU = float(os.environ.get("DSV41_DRAFT_TAU", "1") or 1)


def install(module):
    """sglang.srt.speculative.dspark_components.dspark_draft_sampler"""
    if TAU == 1.0:
        return
    cls = getattr(module, "DsparkDraftSampler", None)
    if cls is None or not hasattr(cls, "stage_sampling_params"):
        raise RuntimeError("DSV41_DRAFT_TAU: DsparkDraftSampler.stage_sampling_params is gone; engine drifted")
    if getattr(cls, "_dsv41_draft_tau", False):
        return
    cls._dsv41_draft_tau = True
    orig = cls.stage_sampling_params

    def stage_sampling_params(self, *, bs, sampling_info):
        orig(self, bs=bs, sampling_info=sampling_info)
        if self.folded_sampling and self.temperatures is not None and sampling_info is not None:
            self.temperatures[:bs].mul_(TAU)

    cls.stage_sampling_params = stage_sampling_params
    print(f"[draft_tau] draft temperature x{TAU}", flush=True)
