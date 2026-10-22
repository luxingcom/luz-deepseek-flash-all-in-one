"""Functional probe for the recipe tokenization path.

Run inside the production container:
    docker exec -i r3prod-head python3 - < recipe_probe.py

It exercises the same encoder imports as serving_chat.py and checks that the
recipe IDs are byte-identical to whole-string tokenization for a plain chat
turn.  Output's final line is JSON; exit 0 only when the recipe path works.
"""
import json
import sys

sys.path.insert(0, "/opt/dsv41/adapter")

try:
    from sglang.srt.entrypoints.openai import encoding_dsv41
    import dsv41_recipe
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        "/models/DeepSeek-V4.1-Flash", trust_remote_code=False
    )
    messages = [{"role": "user", "content": "recipe health probe"}]
    real_input, _media = encoding_dsv41.encode_messages(
        messages,
        thinking_mode="chat",
        reasoning_effort=None,
        return_multi_modal_data=True,
    )
    recipe_ids = dsv41_recipe.encode_prompt_ids(
        messages, real_input, "chat", None, tok
    )
    tokenizer_ids = tok.encode(real_input)
    equal = recipe_ids is not None and recipe_ids == tokenizer_ids
    print(
        json.dumps(
            {
                "ok": equal,
                "recipe_ids": None if recipe_ids is None else len(recipe_ids),
                "tokenizer_ids": len(tokenizer_ids),
                "equal": equal,
            }
        ),
        flush=True,
    )
    sys.exit(0 if equal else 1)
except Exception as exc:  # noqa: BLE001 - probe must report, not crash the shell
    print(
        json.dumps(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        ),
        flush=True,
    )
    sys.exit(1)
