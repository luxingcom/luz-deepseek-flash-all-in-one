"""FL6 KV-recall fix (QA31-20261013 cp30 0/3): SWA interior retirement + match retract.

Root cause: DSV4.1 hybrid radix reuse is gated on the tail sliding-window SWA
KV staying alive; chunked prefill commits one SWA window page per chunk
boundary into the tree, so the SWA pool (125,440 tokens under T256) saturates
at >=~21% fill (QA31 fill30: swa_evictable 121,344, avail 3,072) and
LRU-tombstones the recall-critical final tails -> replay cached=0 while the
FULL KV is resident (FL6 cp30 0/3; anchor 20.83% load was 3/3).

Fix B1 (retire interior): a finished request's branch keeps only its final
tail window live; interior chunk-boundary SWA pages are tombstoned and their
slots returned. The owner never reads them (bounded replay floors the SWA
window at each chunk tail), so recall survives any load the FULL pool holds.
Fix A (match retract): a FULL-resident branch with a dead SWA tail matches
prefix-(window+page, page-aligned) instead of zero; the re-prefilled tail
runs the normal extend path with the same bounded-replay semantics as any
original prefill chunk. Insert-side branching (swa_branching_seqlen) then
re-stamps the tail, so the next replay heals.

Gate: DSV41_FL6_RECALL_FIX — unset=stock (dormant), 1/on=both fixes,
retire=B1 only, retract=A only. Refuses to patch (raises) when the engine's
symbols drift from the 79cafec0 fingerprints checked below.
"""

import inspect
import os

_TRITON = None

_TREE_CORE_SENTINELS = (
    "def _match_prefix_helper(",
    "best_match_device_value_len = len(value)",
    "full_kv_hit_length += prefix_len",
)
_SWA_SENTINELS = (
    "def cleanup_after_caching_req(",
    "insert_result is not None",
    "swa_branch_inserted",
)


def _mode():
    raw = os.environ.get("DSV41_FL6_RECALL_FIX", "")
    raw = raw.strip().lower()
    if raw in ("", "0", "off", "false"):
        return None
    if raw in ("retire",):
        return "retire"
    if raw in ("retract",):
        return "retract"
    return "both"  # 1 / on / true / anything else non-empty


def _check_drift(module, sentinels, name):
    src = inspect.getsource(module)
    for s in sentinels:
        if s not in src:
            raise RuntimeError(
                f"[fl6_recall] {name} drifted from 79cafec0 fingerprint "
                f"(missing sentinel {s!r}); refusing to patch"
            )


def _retract_tokens(comp):
    """Page-aligned window+page retract for tree-resident SWA components."""
    window = comp.sliding_window_size
    if not window:
        return 0
    alloc = comp.cache.token_to_kv_pool_allocator
    if getattr(alloc, "swa_req_ring", False):
        return 0  # per-request-ring layout never stores SWA in the tree
    page = comp.tree_core.page_size
    return ((window + 2 * page - 1) // page) * page


def _retire_interior_windows(comp, leaf):
    """Tombstone+free SWA values on `leaf`'s ancestor chain beyond the final
    tail window (keep = 2 x page_ceil(window)).  Skips nodes locked by
    concurrent requests; never touches FULL values."""
    from sglang.srt.mem_cache.unified_cache.components.base import (
        BASE_COMPONENT_TYPE,
    )

    tc = comp.tree_core
    ct = comp.component_type
    root = tc.root_node
    page = tc.page_size
    keep = 2 * ((comp.sliding_window_size + page - 1) // page) * page

    node = leaf
    if isinstance(node, (int,)):
        node = tc.node_by_id(node)
    if node is None or node is root:
        return

    cum_from_end = 0
    cur = node
    while cur is not root and cur is not None:
        seg = len(cur.key)
        top_from_end = cum_from_end + seg
        cd = cur.component_data[ct]
        if top_from_end > keep and cd.value is not None and cd.lock_ref == 0:
            full_value = cur.component_data[BASE_COMPONENT_TYPE].value
            if full_value is not None:
                freed = len(cd.value)
                # Mirror evict_component: free SWA peers via the node's FULL
                # indices (allocator skips slots with no SWA pair); the FULL
                # value itself stays resident.
                tc.component_evictable_size_[ct] -= freed
                lru = tc.lru_lists.get(ct)
                if lru is not None and lru.in_list(cur):
                    lru.remove_node(cur)
                cd.value = None
                cd.metadata.pop("uuid", None)
                comp.cache.token_to_kv_pool_allocator.free_swa(full_value)
        cum_from_end = top_from_end
        cur = cur.parent


def install_swa(module):
    """Hook: sglang.srt.mem_cache.unified_cache.components.swa"""
    mode = _mode()
    if mode is None:
        return
    _check_drift(module, _SWA_SENTINELS, "components/swa.py")
    SWAComponent = module.SWAComponent
    retire_on = mode in ("both", "retire")
    retract_on = mode in ("both", "retract")

    orig_cleanup = SWAComponent.cleanup_after_caching_req

    def cleanup_after_caching_req(self, req, is_finished, insert_result=None, insert_params=None):
        orig_cleanup(self, req, is_finished, insert_result=insert_result, insert_params=insert_params)
        if retire_on and is_finished and insert_result is not None:
            leaf = getattr(insert_result, "last_device_node", None)
            if leaf is not None:
                _retire_interior_windows(self, leaf)

    def fl6_full_retract_tokens(self):
        return _retract_tokens(self) if retract_on else 0

    SWAComponent.cleanup_after_caching_req = cleanup_after_caching_req
    SWAComponent.fl6_full_retract_tokens = fl6_full_retract_tokens
    print(
        f"[fl6_recall] swa patched (mode={mode}, retire={retire_on}, retract={retract_on})",
        flush=True,
    )


def install(module):
    """Hook: sglang.srt.mem_cache.unified_cache.unified_tree_core"""
    mode = _mode()
    if mode is None:
        return
    _check_drift(module, _TREE_CORE_SENTINELS, "unified_tree_core.py")

    from sglang.srt.mem_cache.unified_cache.components.base import (
        BASE_COMPONENT_TYPE,
        ComponentType,
    )

    UnifiedTreeCore = module.UnifiedTreeCore

    def _match_prefix_helper(self, key):
        # Stock walk (79cafec0) + node trail and the FL6 retract cut at the end.
        node = self.root_node
        key_offset = 0
        child_key = key.child_key_at(key_offset, self.page_size)
        value = []
        trail = []  # FL6: node per value chunk, for the retract cut
        best_match_node = node
        best_match_device_node = node
        best_match_device_value_len = 0
        full_kv_hit_length = 0
        action = None
        separate_device_match = self.enable_hicache
        if separate_device_match:
            validators = tuple(comp.create_match_validator() for comp in self.components)
            device_validators = tuple(
                comp.create_match_validator(match_device_only=True)
                for comp in self.components
            )
        else:
            validators = tuple(
                comp.create_match_validator(match_device_only=True)
                for comp in self.components
            )

        def _all_valid(validators, node):
            return all([v(node) for v in validators])

        def _update_best_if_valid(node):
            nonlocal best_match_node
            nonlocal best_match_device_value_len, best_match_device_node
            matched = _all_valid(validators, node)
            if matched:
                best_match_node = node

            if not separate_device_match:
                if matched:
                    best_match_device_value_len = len(value)
                    best_match_device_node = node
                return
            if _all_valid(device_validators, node):
                best_match_device_value_len = len(value)
                best_match_device_node = node

        while key_offset < len(key) and child_key in node.children:
            child = node.children[child_key]

            # HiCache: dead node (evicted + not backuped) — stop traversal
            if child.evicted and not child.backuped:
                break

            prefix_len = child.key.match_at(key, key_offset, page_size=self.page_size)
            full_kv_hit_length += prefix_len
            if prefix_len < len(child.key):
                node, action = self._split_node(child.key, child, prefix_len)
                if not node.evicted:
                    value.append(node.component_data[BASE_COMPONENT_TYPE].value)
                    trail.append(node)
                _update_best_if_valid(node)
                break

            if not child.evicted:
                value.append(child.component_data[BASE_COMPONENT_TYPE].value)
                trail.append(child)
            node = child
            _update_best_if_valid(node)
            key_offset += prefix_len
            if key_offset < len(key):
                child_key = key.child_key_at(key_offset, self.page_size)

        # ---- FL6 fix A: FULL-resident retract when the SWA tail is dead. ----
        if not separate_device_match and not self.is_eagle:
            swa_comp = None
            for comp in self.components:
                if comp.component_type == ComponentType.SWA and hasattr(
                    comp, "fl6_full_retract_tokens"
                ):
                    swa_comp = comp
                    break
            if swa_comp is not None:
                retract = swa_comp.fl6_full_retract_tokens()
                cut = (full_kv_hit_length // self.page_size) * self.page_size - retract
                if retract and cut > 0:
                    boundary = 0
                    for t in value[:best_match_device_value_len]:
                        boundary += len(t)
                    if cut > boundary:
                        k = 0
                        cum = 0
                        for i, t in enumerate(value):
                            if cum + len(t) > cut:
                                break
                            cum += len(t)
                            k = i + 1
                        if k > 0:
                            best_match_device_value_len = k
                            best_match_device_node = trail[k - 1]
                            best_match_node = trail[k - 1]

        return (
            value,
            best_match_node,
            best_match_device_node,
            best_match_device_value_len,
            full_kv_hit_length,
            action,
        )

    UnifiedTreeCore._match_prefix_helper = _match_prefix_helper
    print(f"[fl6_recall] tree_core patched (mode={mode})", flush=True)
