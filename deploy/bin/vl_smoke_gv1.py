#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vl_smoke_gv1.py — VL-NATIVE G-V1 冒烟门量具（VL-NATIVE-WINCARD-20261013 §5 G-V1；冻结判读线）。

用例集（双源合成；--light=阶梯复跑版〔S4 每级=官方 2 图对+canary+image_tokens〕）：
  ①knapcio 双形状图（PIL 绘 3024×588 红圆左+蓝方右；断言=red/circle/blue/square+
    左右次序；锚=<source-repo>/boot.py:165-185 逐字式）
  ②T13 官方 2 图对（carrots+corn；断言=两食材语义）
  ③自建 OCR（s3_digits_742「图写了哪三个数字」；断言=7/4/2 序）
  ④自建双图比较（d2「第二张比第一张多几根」；断言=2/5/3——跨图计数=更强语义判据）
  ⑤文本 canary×3（北京 temp0；FL6-PROMO lib.sh smoke3 同式；mm 靴文本面自证）
满额断言：usage.prompt_tokens_details.image_tokens == per_image×n_images
  （V4.1=1024/图；V4.0exp=384/图——各模型政策钉，不跨模型对表数值）。
出口：0=全绿；1=语义/断言红；2=HTTP 红/引擎异常。结果 JSONL+summary 落窗 bench。
用法：python3 vl_smoke_gv1.py --port 8898 --model deepseek-v4.1-flash --per-image 1024 \
        --out ~/luz030-opt-campaign/logs/VL-NATIVE-20261013/bench [--light] [--tag L1]
"""
import argparse, base64, io, json, os, sys, time, urllib.request, urllib.error

T17 = "/home/liux***ya/luz030-opt-campaign/logs/T17-20261006"
MAT, SB = f"{T17}/vl-materials", f"{T17}/vl-selfbuilt"


def datauri(path):
    mime = "image/png" if path.endswith(".png") else "image/jpeg"
    return "data:" + mime + ";base64," + base64.b64encode(open(path, "rb").read()).decode()


def knapcio_dual_shape_uri():
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (3024, 588), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((200, 100, 588, 488), fill="red")
    draw.rectangle((2400, 100, 2788, 488), fill="blue")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def chat(base, body, timeout=600):
    req = urllib.request.Request(base + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        d["_sec"] = round(time.time() - t0, 2)
        d["_http"] = 200
        return d
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_error_body": e.read().decode(errors="replace")[:400],
                "_sec": round(time.time() - t0, 2)}
    except Exception as e:
        return {"_http": -1, "_error_body": repr(e)[:400], "_sec": round(time.time() - t0, 2)}


def img_msg(model, text, uris, max_tokens=384):
    parts = [{"type": "text", "text": text}]
    for u in uris:
        parts.append({"type": "image_url", "image_url": {"url": u}})
    # thinking 停用 kwarg（knapcio boot.py 同式）：L1/L2 级无 --reasoning-parser=>
    # 模型思维链若不禁会吞 max_tokens；判据面=content 直答
    return {"model": model, "messages": [{"role": "user", "content": parts}],
            "max_tokens": max_tokens, "temperature": 0,
            "chat_template_kwargs": {"thinking": False}}


def txt_msg(model, text, max_tokens=16):
    return {"model": model, "messages": [{"role": "user", "content": text}],
            "max_tokens": max_tokens, "temperature": 0,
            "chat_template_kwargs": {"thinking": False}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="8898")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--per-image", type=int, default=1024)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="L1")
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--no-sat", action="store_true",
                    help="勘正 5②：全用例动态计费判读（0<v≤cap）——V4.0exp 384 政策=预算内"
                         "动态计费（3024×588 实测 340<384 非帽满），满额断言面不适用该臂")
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"

    cases = []  # (tag, body, n_images, judge, saturating)
    kc = knapcio_dual_shape_uri()
    # saturating=True=图设计为打满 per_image 政策帽（knapcio 3024×588=1.78M px>min_pixels
    # 295936→1024 帽满额）；False=小图按分辨率动态计费（断言=0<v≤帽，值入档）
    cases.append(("knapcio-dualshape",
                  img_msg(a.model, "Describe the two colored shapes and their left-to-right order. Be concise.", [kc]),
                  1,
                  lambda c: judge_knapcio(c), True))
    off = [datauri(f"{MAT}/carrots.jpeg"), datauri(f"{MAT}/corn.jpeg")]
    cases.append(("official-pair",
                  img_msg(a.model, "请按“第一张、第二张”的顺序回答：第一张图和第二张图中分别是什么食材？它们通常食用的部位分别是什么？", off),
                  2,
                  lambda c: judge_official(c), False))
    if not a.light:
        # VL-NATIVE G-V5 面（窗卡：自建 3 图 s1/s3/d2 精简版；s1=红色单形状）
        cases.append(("s1-shape",
                      img_msg(a.model, "图中是什么图形？什么颜色？请用一句话回答。", [datauri(f"{SB}/s1_red_circle.png")]),
                      1, lambda c: judge_s1(c), False))
        cases.append(("s3-ocr",
                      img_msg(a.model, "图中写了哪三个数字？按从左到右顺序回答。", [datauri(f"{SB}/s3_digits_742.png")]),
                      1, lambda c: judge_seq(c, "742"), False))
        cases.append(("d2-dual-count",
                      img_msg(a.model, "第一张图中有几根竖条？第二张图中有几根竖条？第二张比第一张多几根？",
                              [datauri(f"{SB}/d2a_two_vbars.png"), datauri(f"{SB}/d2b_five_vbars.png")]),
                      2, lambda c: judge_seq(c, "2") and judge_seq(c, "5") and judge_seq(c, "3"), False))

    results, http_red, sem_red = [], 0, 0
    canary_ok = 0
    for tag, body, n_img, judge, saturating in cases:
        saturating = saturating and not a.no_sat  # 勘正 5②：--no-sat ⇒ 全用例动态计费判读
        d = chat(base, body)
        rec = {"tag": tag, "http": d.get("_http"), "sec": d.get("_sec")}
        if d.get("_http") != 200:
            rec["error"] = d.get("_error_body", "")[:300]
            http_red += 1
            results.append(rec)
            print(f"[{tag}] HTTP={rec['http']} RED: {rec['error'][:120]}", flush=True)
            continue
        m = d["choices"][0]["message"]
        u = d.get("usage", {})
        det = (u.get("prompt_tokens_details") or {})
        it = det.get("image_tokens")
        cap = a.per_image * n_img
        rec.update({"content": (m.get("content") or "")[:400],
                    "reasoning_len": len(m.get("reasoning_content") or ""),
                    "prompt_tokens": u.get("prompt_tokens"),
                    "image_tokens": it,
                    "cap": cap, "saturating": saturating})
        ok_sem = judge((m.get("content") or "") + (m.get("reasoning_content") or ""))
        if saturating:
            ok_tok = (it == cap)                    # 满额断言（政策帽饱和图=knapcio 式）
        else:
            ok_tok = (isinstance(it, int) and 0 < it <= cap)  # 动态计费面=带内即绿（值入档）
        rec["sem_ok"], rec["image_tokens_ok"] = bool(ok_sem), bool(ok_tok)
        if not ok_sem:
            sem_red += 1
        results.append(rec)
        print(f"[{tag}] http=200 sec={rec['sec']} pt={rec['prompt_tokens']} "
              f"img_tok={it}/{cap}{'SAT' if saturating else ''} "
              f"sem={'OK' if ok_sem else 'RED'} head={repr(rec['content'][:80])}", flush=True)

    for i in range(1, 4):
        d = chat(base, txt_msg(a.model, "中国的首都是哪座城市？只回答城市名。"))
        ok = False
        if d.get("_http") == 200:
            c = (d["choices"][0]["message"].get("content") or "").strip()
            ok = ("北京" in c)
            if ok:
                canary_ok += 1
        results.append({"tag": f"canary{i}", "http": d.get("_http"),
                        "content": (d.get("choices", [{}])[0].get("message", {}).get("content") or "")[:40] if d.get("_http") == 200 else d.get("_error_body", "")[:120],
                        "ok": ok})
        print(f"[canary{i}] http={d.get('_http')} ok={ok}", flush=True)

    canary_green = canary_ok == 3
    green = (http_red == 0) and (sem_red == 0) and canary_green and all(
        r.get("image_tokens_ok") for r in results if "image_tokens_ok" in r)
    summary = {"tag": a.tag, "model": a.model, "per_image_policy": a.per_image, "light": a.light,
               "n_cases": len(cases), "http_red": http_red, "sem_red": sem_red,
               "canary": f"{canary_ok}/3", "green": green,
               "image_tokens_readings": {r["tag"]: r.get("image_tokens") for r in results if "image_tokens" in r}}
    out = a.out if a.out.endswith(".jsonl") else a.out + f"/gv1-{a.tag}.jsonl"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "a", encoding="utf-8") as fp:
        for r in results:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    summ = out.replace(".jsonl", ".summary.json")
    json.dump(summary, open(summ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"G-V1[{a.tag}] green={green}（http_red={http_red} sem_red={sem_red} canary={canary_ok}/3 "
          f"image_tokens={summary['image_tokens_readings']}）→ {out}", flush=True)
    sys.exit(0 if green else (2 if http_red else 1))


def judge_s1(combined):
    c = combined.lower()
    ok_shape = ("圆" in combined) or ("circle" in c)
    ok_color = ("红" in combined) or ("red" in c)
    return ok_shape and ok_color


def judge_knapcio(combined):
    t = combined.lower()
    if not all(w in t for w in ("red", "circle", "blue", "square")):
        return False
    # 左右次序：red/circle 先于 blue/square（图左红圆+图右蓝方）
    pos = [t.find(w) for w in ("red", "circle", "blue", "square")]
    if -1 in pos:
        return False
    return max(pos[0], pos[1]) < min(pos[2], pos[3])


def judge_official(combined):
    c = combined
    ok1 = ("胡萝卜" in c) or ("carrot" in c.lower())
    ok2 = ("玉米" in c) or ("corn" in c.lower())
    return ok1 and ok2


def judge_seq(combined, seq):
    # 勘正 5①：数字序列判读容分隔符（V4.0exp 答形「7, 4, 2」=742 语义对；
    #   归一=仅保字母数字后再匹配——s3/d2 判读线不变）
    norm = "".join(ch for ch in combined if ch.isalnum())
    return seq in norm


if __name__ == "__main__":
    main()
