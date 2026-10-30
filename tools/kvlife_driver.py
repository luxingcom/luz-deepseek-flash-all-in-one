#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kvlife_driver — KV 缓存生命周期与召回专项 driver（KV-LIFECYCLE-TEST-CARD-20261009 §2.5 实现律）。

设计律五条（卡 §2.5，全部落码）：
  ①行键集完备律：一切行（PASS/FAIL/SKIP/REJECT/超时）落盘时补全键集
    （prompt_tokens/cached_tokens/ttft_s…=0/None），聚合一律 .get()——规避
    c16_600k_driver 被拒行 KeyError 前科（RATIFY §四.4.1 工具缺口注记）。
  ②400 分类律：HTTPError 体 json 解析 reject reason 记行继续不中断。
  ③校准律：calib 相用合成参考文本测 zh/en 字/token 密度（不污染语料 cache）；
    填充相每行实测 chars_per_token 滚动记录；占池进度以服务端 /metrics 为准。
  ④metrics 快照律：每 N=10 发+相位边界拉 /metrics 存 jsonl（kv_available/
    evictable/used、swa 同族、cache_hit_rate、num_retracted…）。
    （cache_hit_rate 裸快照=上游 #45119 缺陷面，只存原始值不作判据——口径判读走
    tools/obs/cache_hit_caliber.py 计数器正典。）
  ⑤文档寻址律：doc 文本=plan 确定性纯函数拼装（盐头+章段+问题尾），落 md5；
    召回/逐出相凭 doc_id 重发逐字同文。

继承 c16 骨架：WaterSentry（1s 哨兵+/abort_request 幂等全中止）+http timeout
≥5400s+客户端 T×L 预门（--tl-budget 镜像 admission limit）。

文档结构（卡 §1.1）：D(i) = [盐头 ~32tok] + 章界胶水串 + [问题尾]。同书文档共享
盐头（书干 stub，页级）；不同书盐头唯一（防跨文档意外共头）。doc 章段互不相交
（prefill 墙经济学：发送量=净新增量；累积链式拼装会 ×k²/2 放大发送量撑爆填满
墙钟——如实注记于窗档）。

自测：python3 tools/kvlife_driver.py --selfcheck（离线零发包）
"""
import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

# ---------------- 语料分段（prep 相） ----------------

GUT_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*", re.I)
GUT_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*", re.I)
ZH_CHAP = re.compile(r"^\s*(第[零一二三四五六七八九十百千万两0-9]{1,12}[回章節节卷][^\n]{0,60})\s*$", re.M)
EN_CHAP = re.compile(r"^\s*(CHAPTER\s+[IVXLCDM0-9]+\.?[^\n]{0,70}|Chapter\s+\d+[^\n]{0,70})\s*$", re.M)


def strip_gutenberg(text):
    m = GUT_START.search(text)
    if m:
        text = text[m.end():]
    m = GUT_END.search(text)
    if m:
        text = text[:m.start()]
    return text


def split_chapters(text, lang):
    """返回 [(header, body)]；header=回目/章节句（章界胶水，真实排版惯例）。"""
    pat = ZH_CHAP if lang == "zh" else EN_CHAP
    marks = list(pat.finditer(text))
    if len(marks) >= 2:
        chapters = []
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[m.start():end].strip()
            if len(body) >= 400:
                chapters.append((m.group(1).strip(), body))
        if chapters and sum(len(b) for _, b in chapters) >= 0.5 * len(text):
            return chapters
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paras) < 2:  # 无空行分段的书（中文单换行排版）退单换行
        paras = [p for p in text.strip().split("\n") if p.strip()]
    if len(paras) < 2:  # 末路回退：句号边界硬切 ~4k
        paras = [text.strip()[i:i + 4000] for i in range(0, len(text.strip()), 4000)]
    chapters, buf, sz = [], [], 0
    for p in paras:
        buf.append(p)
        sz += len(p)
        if sz >= 4000:
            chapters.append((f"[section {len(chapters) + 1}]", "\n\n".join(buf).strip()))
            buf, sz = [], 0
    if buf:
        chapters.append((f"[section {len(chapters) + 1}]", "\n\n".join(buf).strip()))
    return chapters


def norm_book(title, raw_path, lang, out_norm_dir):
    with open(raw_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    # 内容语言检测（防 ascii 文件名中文书误判）
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text[:50000]))
    lang = "zh" if cjk > 5000 else lang
    text = strip_gutenberg(text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    chapters = split_chapters(text, lang)
    book_id = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title)[:40].strip("_").lower()
    if not book_id:
        book_id = "b" + hashlib.md5(title.encode("utf-8")).hexdigest()[:10]
    parts = [f"《{title}》全文起始。" if lang == "zh" else f"The Complete Text of {title}."]
    idxs = []
    for h, b in chapters:
        idxs.append(len("\n\n".join(parts)))
        parts.append(f"{h}\n{b}")
    norm = "\n\n".join(parts)
    norm_path = os.path.join(out_norm_dir, f"{book_id}.norm.txt")
    with open(norm_path, "w", encoding="utf-8") as f:
        f.write(norm)
    return {"book_id": book_id, "title": title, "lang": lang, "norm_path": norm_path,
            "md5": hashlib.md5(norm.encode("utf-8")).hexdigest(),
            "chars": len(norm), "n_chapters": len(chapters),
            "chapter_offsets": idxs}


def cmd_prep(args):
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    norm_dir = os.path.join(out_dir, "norm")
    os.makedirs(norm_dir, exist_ok=True)
    books = []
    for fn in sorted(os.listdir(args.raw_dir)):
        p = os.path.join(args.raw_dir, fn)
        if not os.path.isfile(p) or os.path.getsize(p) < 60000:
            continue
        if re.search(r"[\u4e00-\u9fff]", fn):
            lang, title = "zh", os.path.splitext(fn)[0]
        elif fn.endswith(".txt"):
            lang = "en"
            title = os.path.splitext(re.sub(r"\.pg\d+$", "", fn))[0].replace("_", " ").title()
        else:
            continue
        b = norm_book(title, p, lang, norm_dir)
        books.append(b)
        print(f"[prep] {b['book_id']:26s} lang={lang} chars={b['chars']:9d} "
              f"chapters={b['n_chapters']:4d} md5={b['md5'][:8]}")
    books.sort(key=lambda b: -b["chars"])
    with open(os.path.join(out_dir, "books.jsonl"), "w", encoding="utf-8") as f:
        for b in books:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    tot = sum(b["chars"] for b in books)
    print(f"[prep] books={len(books)} total_chars={tot} → {out_dir}/books.jsonl")
    return 0

# ---------------- 计划（plan 相） ----------------

def load_books(path):
    books = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                books.append(json.loads(ln))
    return books


class SpanAlloc:
    """每书顺序不相交章段分配器（章界对齐；书尾 ≥25% 目标即收=书尾浪费收敛）。"""

    def __init__(self, tail_frac=0.25):
        self.st = {}
        self.tail_frac = tail_frac

    def take(self, book, target_chars):
        s = self.st.get(book["book_id"], 0)
        if s >= book["chars"] - 2000:
            return None
        off = s
        end = min(off + target_chars, book["chars"])
        for o in book.get("chapter_offsets", []):
            if o > end:
                end = min(o, book["chars"])
                break
        else:
            end = book["chars"]
        if end - off < target_chars * self.tail_frac:
            return None
        self.st[book["book_id"]] = end
        return (off, end)


def cmd_plan(args):
    books = load_books(args.books)
    run_id = args.run_id
    cpt = {"zh": args.cpt_zh, "en": args.cpt_en}

    class LangAlloc(SpanAlloc):
        def take_tok(self, book, target_tokens):
            return self.take(book, int(target_tokens * cpt.get(book["lang"], args.cpt_en)))

    alloc = LangAlloc()
    holdout, pressure, fill = [], [], list(books)
    need_h, need_p = args.holdout_chars, args.pressure_chars
    while fill and need_h > 0:
        b = fill.pop()
        holdout.append(b)
        need_h -= b["chars"]
    while fill and need_p > 0:
        b = fill.pop()
        pressure.append(b)
        need_p -= b["chars"]
    docs, hdocs, pdocs, sdocs = [], [], [], []
    ladder = [int(x) for x in args.ladder.split(",") if x.strip()]
    # 阶梯档：从填充主流（大书在前）顺序取段——发送序=ladder 序（验收①渐进面）；
    # 空间序与主力段连续（同书异段不相交，盐头同书=书干 stub）。
    stream = list(fill)
    si = [0]

    def stream_take(target_tokens):
        while si[0] < len(stream):
            book = stream[si[0]]
            span = alloc.take_tok(book, target_tokens)
            if span:
                return book, span
            si[0] += 1
        return None, None

    for size in ladder:
        for _ in range(args.shots_per_ladder):
            book, span = stream_take(size)
            if not span:
                break
            docs.append({"doc_id": f"L{len(docs) + 1:04d}", "phase": "ladder", "size": size,
                         "book": book["book_id"], "salt": book["book_id"], "span": span,
                         "target_tokens": size})
    # 主力段：主流续切
    n_main = 0
    while True:
        book, span = stream_take(args.main_doc_tokens)
        if not span:
            break
        n_main += 1
        docs.append({"doc_id": f"M{n_main:04d}", "phase": "main", "size": args.main_doc_tokens,
                     "book": book["book_id"], "salt": book["book_id"], "span": span,
                     "target_tokens": args.main_doc_tokens})
    # holdout（冷基线）：小档×3×2+主力档×2
    for size in [s for s in ladder if s <= 32768][:2] + [args.main_doc_tokens]:
        n = 3 if size <= 32768 else 2
        got = 0
        for b in holdout:
            while got < n:
                span = alloc.take_tok(b, size)
                if span is None:
                    break
                hdocs.append({"doc_id": f"H{len(hdocs) + 1:04d}", "phase": "holdout", "size": size,
                              "book": b["book_id"], "salt": f"ho-{b['book_id']}-{len(hdocs) + 1}", "span": span,
                              "target_tokens": size})
                got += 1
            if got >= n:
                break
    # pressure（真实书）
    for b in pressure:
        while True:
            span = alloc.take_tok(b, args.main_doc_tokens)
            if span is None:
                break
            pdocs.append({"doc_id": f"P{len(pdocs) + 1:04d}", "phase": "pressure", "size": args.main_doc_tokens,
                          "book": b["book_id"], "salt": f"pr-{b['book_id']}", "span": span,
                          "target_tokens": args.main_doc_tokens})
    # 盐书（轨 C 压池放大器；复用 fill 大书首段+唯一盐头=零前缀共享净占池；披露用）
    if fill:
        big = fill[0]
        for i in range(args.salt_books):
            span = (0, min(int(args.main_doc_tokens * cpt.get(big["lang"], args.cpt_en)), big["chars"]))
            sdocs.append({"doc_id": f"S{i + 1:04d}", "phase": "salt", "size": args.main_doc_tokens,
                          "book": big["book_id"], "salt": f"c-{run_id}-{i + 1}", "span": span,
                          "target_tokens": args.main_doc_tokens})
    plan = {"run_id": run_id, "model": args.model, "pool_tokens": args.pool_tokens,
            "main_doc_tokens": args.main_doc_tokens, "chars_per_token_prior": cpt,
            "docs": docs, "holdout": hdocs, "pressure": pdocs, "salt": sdocs}
    out = {"plan": plan, "books": {b["book_id"]: {"norm_path": b["norm_path"], "md5": b["md5"],
                                                  "chars": b["chars"], "lang": b["lang"],
                                                  "title": b["title"]} for b in books}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    fill_tok = sum(int((d["span"][1] - d["span"][0]) / cpt.get(next((b for b in books if b["book_id"] == d["book"]), {}).get("lang", "en"), args.cpt_en)) for d in docs)
    print(f"[plan] model={args.model} pool={args.pool_tokens} ladder={sum(1 for d in docs if d['phase'] == 'ladder')} "
          f"main={n_main} holdout={len(hdocs)} pressure={len(pdocs)} salt={len(sdocs)} "
          f"fill_tok≈{fill_tok}（先验）")
    return 0

# ---------------- 运行时基件 ----------------

class WaterSentry(threading.Thread):
    def __init__(self, base, abort_m, sample_s=1.0):
        super().__init__(daemon=True)
        self.base, self.abort_m, self.sample_s = base, abort_m, sample_s
        self.lowest = None
        self.before = None
        self.aborted = False
        self.stop = threading.Event()

    def read_m(self):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
        except OSError:
            return None
        return None

    def abort_all(self):
        if self.aborted:
            return
        self.aborted = True
        try:
            req = urllib.request.Request(self.base.rstrip("/") + "/abort_request",
                                         data=json.dumps({"abort_all_requests": True}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=30).read()
        except Exception:
            pass

    def run(self):
        self.before = self.read_m()
        self.lowest = self.before
        while not self.stop.is_set():
            m = self.read_m()
            if m is not None:
                if self.lowest is None or m < self.lowest:
                    self.lowest = m
                if m < self.abort_m:
                    self.abort_all()
                    return
            self.stop.wait(self.sample_s)


class Client:
    def __init__(self, base, model, timeout):
        self.base, self.model, self.timeout = base, model, timeout

    def ask(self, prompt, max_tokens):
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": max_tokens, "temperature": 0.0, "stream": True,
                   "stream_options": {"include_usage": True}}
        req = urllib.request.Request(self.base.rstrip("/") + "/v1/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        ttft = None
        chunks = []
        pt = ct = cached = 0
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                u = obj.get("usage") or {}
                if u:
                    pt = u.get("prompt_tokens", pt) or pt
                    ct = u.get("completion_tokens", ct) or ct
                    ptd = (u.get("prompt_tokens_details") or {})
                    cached = ptd.get("cached_tokens", cached) or cached
                for ch in obj.get("choices", []):
                    delta = (ch.get("delta") or {}).get("content") or ""
                    if delta:
                        if ttft is None:
                            ttft = time.time() - t0
                        chunks.append(delta)
        return "".join(chunks), pt, ct, cached, ttft, time.time() - t0


MET_KEYS = ("kv_available_tokens", "kv_evictable_tokens", "kv_used_tokens",
            "swa_available_tokens", "swa_evictable_tokens", "swa_used_tokens",
            "full_token_usage", "swa_token_usage", "cache_hit_rate",  # cache-hit-caliber: raw-snapshot
            "cached_tokens_total", "num_retracted_reqs", "max_total_num_tokens")


def metrics_snapshot(base):
    out = {"ts": round(time.time(), 1)}
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/metrics", timeout=10) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace")
                if line.startswith("#") or not line.strip():
                    continue
                name = line.split("{")[0].split(" ")[0]
                for k in MET_KEYS:
                    if name.endswith(k):
                        try:
                            out[k] = float(line.rsplit(" ", 1)[1].strip())
                        except (ValueError, IndexError):
                            pass
                        break
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:120]
    return out


def blank_row(doc, extra=None):
    """行键集完备律：一切行全键集（含 SKIP/REJECT/FAIL）。"""
    row = {"doc_id": doc.get("doc_id"), "phase": doc.get("phase"), "book": doc.get("book"),
           "salt": doc.get("salt"), "size": doc.get("size"), "target_tokens": doc.get("target_tokens"),
           "est_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0,
           "hit_ratio": None, "chars_per_token": None, "ttft_s": None, "total_s": None,
           "status": "SKIP", "error": None, "reject_reason": None, "error_body": None,
           "answer_head": "", "weak_ok": None, "md5": None, "tag": doc.get("phase"),
           "ts": round(time.time(), 1)}
    if extra:
        row.update(extra)
    return row


def ask_row(client, doc, prompt, md5, expect, gen_tokens, tl_limit):
    row = blank_row(doc, {"md5": md5})
    if prompt.isascii():
        row["est_tokens"] = int((len(prompt) + 3) / 4)
    else:
        cjk = len(re.findall(r"[^\x00-\x7f]", prompt))
        row["est_tokens"] = int((len(prompt) - cjk) / 4 + cjk / 1.5)
    if tl_limit and row["est_tokens"] > tl_limit * 1.03:
        row["reject_reason"] = f"client-tl-gate est>{tl_limit}"
        return row
    try:
        txt, pt, ct, cached, ttft, tot = client.ask(prompt, gen_tokens)
        row.update({"prompt_tokens": pt, "completion_tokens": ct, "cached_tokens": cached,
                    "ttft_s": round(ttft, 3) if ttft else None,
                    "total_s": round(tot, 3) if tot else None,
                    "answer_head": re.sub(r"\s+", " ", txt or "")[:120],
                    "status": "PASS"})
        if pt:
            row["hit_ratio"] = round(cached / pt, 4)
            row["chars_per_token"] = round(len(prompt) / pt, 4)
        if expect:
            row["weak_ok"] = any(e and e in (txt or "") for e in expect)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001
            pass
        try:
            msg = str((json.loads(body) if body.startswith("{") else {}).get("message") or body)[:220]
        except ValueError:
            msg = body[:220]
        reason = "http-%d" % e.code
        if e.code == 400:
            reason = "admission-400" if re.search(r"admission|context|budget|too (long|large)|limit", msg, re.I) else "bad-request-400"
        row.update({"status": "REJECT", "error": str(e)[:120], "reject_reason": reason, "error_body": msg})
    except Exception as e:  # noqa: BLE001
        row.update({"status": "FAIL", "error": str(e)[:200]})
    return row


class Runner:
    def __init__(self, args, plan_path):
        self.args = args
        with open(plan_path, encoding="utf-8") as f:
            blob = json.load(f)
        self.plan = blob["plan"]
        self.books = blob["books"]
        self.base = args.base
        self.sentry = WaterSentry(args.base, args.water_abort_m, 1.0)
        self.client = Client(args.base, args.model, args.http_timeout)
        self.tl_limit = args.tl_budget // 4096
        self.rundir = args.rundir
        os.makedirs(self.rundir, exist_ok=True)
        self.rows_path = os.path.join(self.rundir, args.rows_name)
        self.met_path = os.path.join(self.rundir, "metrics.jsonl")
        self.sent_ids = set()
        if os.path.exists(self.rows_path):
            with open(self.rows_path, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r0 = json.loads(ln)
                        if r0.get("status") == "PASS":
                            self.sent_ids.add(r0.get("doc_id"))
                    except ValueError:
                        pass
        self.shot_count = 0
        self._mlock = threading.Lock()
        self._wlock = threading.Lock()

    def doc_text(self, doc):
        bk = self.books[doc["book"]]
        with open(bk["norm_path"], encoding="utf-8") as f:
            f.seek(doc["span"][0])
            body = f.read(doc["span"][1] - doc["span"][0])
        zh = bk["lang"] == "zh"
        head = (f"[kvlife-{self.plan['run_id']}-{doc['salt']}] " +
                ("下面是一部文学作品的多章连续文本，作为长文阅读材料。\n" if zh else
                 "Below is a multi-chapter excerpt from a work of literature for long-form reading.\n"))
        tail = ("\n\n问题：上文最后部分的章回（章节）标题是什么？请用一句话简要作答，并提及书名。"
                if zh else
                "\n\nQuestion: What is the chapter heading of the last part above? Answer briefly in one sentence, mentioning the book title.")
        text = head + body + tail
        # 弱校验锚=span 内最后一个章界头 + 书名
        pat = ZH_CHAP if zh else EN_CHAP
        heads = [m.group(1).strip() for m in pat.finditer(body)]
        expect = [bk["title"]] + [h[:14] for h in heads[-2:]]
        return text, expect

    def snap(self, tag):
        m = metrics_snapshot(self.base)
        m["tag"] = tag
        with self._mlock:
            with open(self.met_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        return m

    def progress(self):
        m = metrics_snapshot(self.base)
        avail = m.get("kv_available_tokens")
        if avail is None:
            return None, m
        return 1.0 - avail / self.plan["pool_tokens"], m

    def maybe_snap(self):
        self.shot_count += 1
        if self.shot_count % self.args.snap_every == 0:
            self.snap("periodic")

    def fire(self, doc, gen_tokens, tag=None):
        text, expect = self.doc_text(doc)
        md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
        row = ask_row(self.client, doc, text, md5, expect, gen_tokens, self.tl_limit)
        if tag:
            row["tag"] = tag
        with self._wlock:
            with open(self.rows_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.maybe_snap()
        return row

    def fire_parallel(self, docs, gen_tokens, c, tag=None):
        rows = [None] * len(docs)
        lock = threading.Lock()
        idx = [0]

        def work():
            while True:
                with lock:
                    if idx[0] >= len(docs):
                        return
                    i = idx[0]
                    idx[0] += 1
                rows[i] = self.fire(docs[i], gen_tokens, tag)

        ths = [threading.Thread(target=work) for _ in range(max(1, c))]
        if self.sentry.ident is None:  # 幂等 start（线程只能起一次）
            self.sentry.start()
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        return rows


def flush_cache(base):
    try:
        req = urllib.request.Request(base.rstrip("/") + "/flush_cache", data=b"", method="POST")
        urllib.request.urlopen(req, timeout=60).read()
        return True
    except Exception as e:  # noqa: BLE001
        print("[flush] err:", str(e)[:120])
        return False


# 合成校准文本（不占语料、不污染树：flush 于 calib 尾部收束）
CALIB_ZH = "这是一段用于测量分词密度的参考文本。它不是任何语料书的内容，仅由常见汉字与标点构成，" \
           "模拟中文文学的平均字词分布。句子有长有短，对话与叙述交替出现，如同章回小说的一般样貌。" * 24
CALIB_EN = ("This is a reference passage for measuring tokenizer density. It is not part of any "
            "corpus book, only common English words and punctuation, mimicking the average word "
            "distribution of literary prose. Sentences vary in length; dialogue and narration "
            "alternate as in an ordinary chapter of a novel. ") * 24


def cmd_calib(args):
    r = Runner(args, args.plan)
    m0 = r.snap("calib-pre-flush")
    flush_cache(r.base)
    time.sleep(3)
    m = r.snap("calib-post-flush")
    pool = r.plan["pool_tokens"]
    avail = m.get("kv_available_tokens")
    print(f"[calib] flush 自证：kv_available {m0.get('kv_available_tokens')} → {avail} "
          f"(pool={pool}；{(avail / pool * 100 if avail else 0):.1f}% 回满判读)")
    density = {}
    for lang, txt in (("zh", CALIB_ZH), ("en", CALIB_EN)):
        doc = {"doc_id": f"CAL-{lang}", "phase": "calib", "book": "-", "salt": f"cal-{lang}",
               "size": 0, "target_tokens": 0}
        row = ask_row(r.client, doc, txt, hashlib.md5(txt.encode()).hexdigest(), None, args.gen_tokens, r.tl_limit)
        if row["status"] == "PASS" and row["prompt_tokens"]:
            density[lang] = row["chars_per_token"]
            print(f"[calib] {lang}: chars={len(txt)} tokens={row['prompt_tokens']} "
                  f"chars/token={row['chars_per_token']} ttft={row['ttft_s']}")
        else:
            print(f"[calib] {lang} 红：{row['status']} {row.get('error') or row.get('reject_reason')}")
    flush_cache(r.base)  # calib 尾 flush：树净进填充相
    time.sleep(2)
    r.snap("calib-final-flush")
    with open(os.path.join(r.rundir, "calib.json"), "w", encoding="utf-8") as f:
        json.dump({"density": density, "post_flush_available": avail, "pool": pool},
                  f, ensure_ascii=False, indent=1)
    return 0 if density else 9


def cmd_fill(args):
    r = Runner(args, args.plan)
    pool = r.plan["pool_tokens"]
    target = args.until_pct
    docs = [d for d in r.plan["docs"] if d["doc_id"] not in r.sent_ids]
    if args.limit_per_size is not None:
        # 档位限额：每 target_tokens 组只保留前 N 发（doc_id 序）——时间盒收缩用
        # --single-above：ladder 相大于该档只发 1 发（主力/盐不受限——组键分离）
        seen = {}
        kept = []
        for d in docs:
            k = d["target_tokens"] if d.get("phase") == "ladder" else f"m-{id(d)}"
            seen[k] = seen.get(k, 0) + 1
            cap = 1 if (args.single_above is not None and d.get("phase") == "ladder"
                        and d["target_tokens"] > args.single_above) else args.limit_per_size
            if seen[k] <= cap:
                kept.append(d)
        docs = kept
    if args.append_salt and r.plan["salt"]:
        docs = docs + r.plan["salt"]
    r.snap("fill-start")
    i, stop_reason, log = 0, None, []
    while i < len(docs):
        prog, m = r.progress()
        if target is not None and prog is not None and prog >= (target / 100.0 - 0.025):
            stop_reason = f"progress {prog * 100:.1f}% 达 {target}%-2.5pt 带"
            break
        if m.get("kv_available_tokens") is not None and m["kv_available_tokens"] < args.reserve_tokens:
            stop_reason = f"kv_available {m['kv_available_tokens']:.0f} < reserve {args.reserve_tokens}"
            break
        # checkpoint 逼近批收缩（保 ±3% 带内落地）
        c = args.concurrency
        if target is not None and prog is not None:
            doc_frac = (docs[i]["target_tokens"] / pool) if pool else 0
            gap = target / 100.0 - prog
            if gap < max(0.06, 2.5 * doc_frac * c):
                c = 1
        if docs[i]["target_tokens"] >= 262144:
            c = min(c, 4)  # ≥256k 档 c≤4 纪律
        chunk = docs[i:i + c]
        rows = r.fire_parallel(chunk, args.gen_tokens, c, tag="fill")
        log.extend(rows)
        i += len(chunk)
        done = sum(1 for x in log if x and x.get("status") == "PASS")
        net = sum((x.get("prompt_tokens") or 0) - (x.get("cached_tokens") or 0) for x in log if x)
        print(f"[fill] {i}/{len(docs)} pass={done} net_tok={net} avail={m.get('kv_available_tokens')}", flush=True)
        if r.sentry.aborted:
            stop_reason = "water-sentry abort"
            break
        if rows and all(x and x.get("reject_reason") == "admission-400" for x in rows):
            stop_reason = "all-admission-reject（语料/档位撞 admission 墙）"
            break
    prog, m = r.progress()
    r.snap("fill-stop")
    out = {"phase": "fill", "until_pct": target, "stop_reason": stop_reason,
           "docs_sent": len(log), "final_progress": round(prog, 4) if prog is not None else None,
           "kv_available_tokens": m.get("kv_available_tokens"),
           "water": {"before": r.sentry.before, "lowest": r.sentry.lowest, "aborted": r.sentry.aborted}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _sall_first(lst):
    return sorted(lst, key=lambda d: d["doc_id"])[0]


def pick_hot(plan):
    """最旧三文档：8k 档+32k 档+主力档各一（卡 §2.2：先旧后新序由调用方保）。"""
    docs = plan["docs"]
    main_size = plan["main_doc_tokens"]
    picks = []
    for f in (lambda d: d["target_tokens"] <= 16384,
              lambda d: 16384 < d["target_tokens"] <= 65536,
              lambda d: d["target_tokens"] == main_size):
        m = [d for d in docs if f(d)]
        if m:
            picks.append(_sall_first(m))
    return picks[:3]


def cmd_recall(args):
    r = Runner(args, args.plan)
    r.snap(f"recall-cp{args.checkpoint}-start")
    out = {"checkpoint": args.checkpoint, "cold": [], "hot": []}
    # 冷基线：holdout 文档（未见书）逐发 c=1（TTFT 纯净）；--no-cold=复用前 checkpoint 冷带
    seen_sz = {}
    for d in r.plan["holdout"]:
        if args.no_cold:
            break
        if args.cold_sizes and d["target_tokens"] not in args.cold_sizes:
            continue
        sz = d["target_tokens"]
        seen_sz[sz] = seen_sz.get(sz, 0) + 1
        if args.cold_max_per_size and seen_sz[sz] > args.cold_max_per_size:
            continue
        row = r.fire(d, args.gen_tokens, tag=f"cold-cp{args.checkpoint}")
        out["cold"].append(row)
        print(f"[cold] {d['doc_id']} size={d['target_tokens']} ttft={row.get('ttft_s')} "
              f"hit={row.get('hit_ratio')} status={row.get('status')}", flush=True)
    for d in pick_hot(r.plan):
        row = r.fire(d, args.gen_tokens, tag=f"hot-cp{args.checkpoint}")
        out["hot"].append(row)
        print(f"[hot] {d['doc_id']} size={d['target_tokens']} ttft={row.get('ttft_s')} "
              f"cached={row.get('cached_tokens')}/{row.get('prompt_tokens')} hit={row.get('hit_ratio')}", flush=True)
    r.snap(f"recall-cp{args.checkpoint}-end")
    with open(os.path.join(r.rundir, f"recall_cp{args.checkpoint}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return 0


def cmd_evict(args):
    r = Runner(args, args.plan)
    pool = r.plan["pool_tokens"]
    r.snap("evict-start")
    docs0 = sorted(r.plan["docs"], key=lambda d: d["doc_id"])
    smalls0 = sorted([d for d in docs0 if d["target_tokens"] <= 16384], key=lambda d: d["doc_id"])
    # 刷新臂：无召回 checkpoint 的腿（时间盒裁剪）——压力前重放 smalls[0] 一次，
    #   制造「命中刷新 last_access」的 LRU 保护分支（与 smalls[1] 未刷新形成对照）
    refresh_arm = smalls0[0] if smalls0 else None
    prior_tags = {}
    if os.path.exists(r.rows_path):
        with open(r.rows_path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rr = json.loads(ln)
                except Exception:  # noqa: BLE001
                    continue
                prior_tags.setdefault(rr.get("doc_id"), str(rr.get("tag", "")))
    replayed = prior_tags.get((refresh_arm or {}).get("doc_id"), "").startswith(("hot-", "probe-refresh-arm"))
    if refresh_arm and not replayed:
        row0 = r.fire(refresh_arm, args.gen_tokens, tag="probe-refresh-arm")
        print(f"[refresh-arm] {refresh_arm['doc_id']} hit={row0.get('hit_ratio')} "
              f"ttft={row0.get('ttft_s')}", flush=True)
    press = list(r.plan["pressure"]) + (r.plan["salt"] if args.use_salt else [])
    out = {"pressure_rows": [], "probes": [], "refresh_arm": refresh_arm["doc_id"] if refresh_arm else None}
    target_tok = args.press_tokens if args.press_tokens else int(pool * 0.12)
    acc = 0
    for d in press:
        if acc >= target_tok:
            break
        rows = r.fire_parallel([d], args.gen_tokens, 1, tag="pressure")
        out["pressure_rows"].extend(rows)
        acc += sum((x.get("prompt_tokens") or 0) - (x.get("cached_tokens") or 0) for x in rows if x)
        prog, m = r.progress()
        print(f"[pressure] {d['doc_id']} acc_net={acc} avail={m.get('kv_available_tokens')} "
              f"evictable={m.get('kv_evictable_tokens')}", flush=True)
        if r.sentry.aborted:
            break
    r.snap("pressure-end")
    docs = sorted(r.plan["docs"], key=lambda d: d["doc_id"])
    main_size = r.plan["main_doc_tokens"]
    mains = [d for d in docs if d["target_tokens"] == main_size]
    # 判读序纪律（卡 §2.3 先旧后新+§0.1 命中刷新 last_access）：
    #   probe-oldest = 次早文档（召回相未重发过的最旧分支——D(1)/主力首档在 cp50/80
    #     热召回中被刷新，若取之会假红）
    #   probe-refreshed = D(1)（cp 热召回刷新过——预期仍 hit=「命中刷新 last_access」
    #     LRU 语义对照直证）
    #   probe-newest = 主力档最后入池文档（预期 hit）
    smalls = sorted([d for d in docs if d["target_tokens"] <= 16384], key=lambda d: d["doc_id"])
    oldest = smalls[1] if len(smalls) > 1 else (docs[1] if len(docs) > 1 else docs[0])
    refreshed = smalls[0] if smalls else docs[0]
    newest = mains[-1] if mains else docs[-1]
    mid = docs[len(docs) // 2] if len(docs) > 6 else None
    seq = [(oldest, "probe-oldest"), (refreshed, "probe-refreshed"), (newest, "probe-newest")]
    if mid and mid["doc_id"] not in (oldest["doc_id"], refreshed["doc_id"], newest["doc_id"]):
        seq.append((mid, "probe-mid"))
    for d, tag in seq:
        row = r.fire(d, args.gen_tokens, tag=tag)
        out["probes"].append(row)
        print(f"[{tag}] {d['doc_id']} cached={row.get('cached_tokens')}/{row.get('prompt_tokens')} "
              f"hit={row.get('hit_ratio')} ttft={row.get('ttft_s')}", flush=True)
    r.snap("evict-end")
    with open(os.path.join(r.rundir, "evict.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("evict:", json.dumps([(p.get("tag"), p.get("hit_ratio"), p.get("ttft_s")) for p in out["probes"]]))
    return 0


def cmd_report(args):
    rundir = args.rundir
    rows = []
    path = os.path.join(rundir, args.rows_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    pass

    def med(vals):
        vs = sorted(v for v in vals if v is not None)
        if not vs:
            return None
        n = len(vs)
        return vs[n // 2] if n % 2 else round((vs[n // 2 - 1] + vs[n // 2]) / 2, 3)

    cold = [x for x in rows if str(x.get("tag", "")).startswith("cold-") and x.get("ttft_s")]
    hot = [x for x in rows if str(x.get("tag", "")).startswith("hot-") and x.get("ttft_s")]
    table = []
    for h in hot:
        size = h.get("target_tokens") or 0
        peers = [c for c in cold if c.get("target_tokens") and abs(c["target_tokens"] - size) / max(size, 1) < 0.35]
        tc, th = med([p.get("ttft_s") for p in peers]), h.get("ttft_s")
        table.append({"doc": h.get("doc_id"), "size_tok": size,
                      "hit_ratio": h.get("hit_ratio"), "cached_tok": h.get("cached_tokens"),
                      "prompt_tok": h.get("prompt_tokens"), "ttft_hot_s": th,
                      "ttft_cold_med_s": tc, "cold_n": len(peers),
                      "ttft_ratio": round(th / tc, 3) if th and tc else None,
                      "saving_pct": round((1 - th / tc) * 100, 1) if th and tc else None,
                      "weak_ok": h.get("weak_ok"), "checkpoint": h.get("tag", "")})
    probes = [x for x in rows if str(x.get("tag", "")).startswith("probe-")]
    fill_rows = [x for x in rows if x.get("tag") == "fill"]
    fill_pass = [x for x in fill_rows if x.get("status") == "PASS"]
    rep = {"model": args.model,
           "fill": {"shots": len(fill_rows), "pass": len(fill_pass),
                    "net_tokens": sum((x.get("prompt_tokens") or 0) - (x.get("cached_tokens") or 0) for x in fill_pass),
                    "new_doc_hit_max": max([x.get("hit_ratio") or 0 for x in fill_pass] + [0]),
                    "rejects": sum(1 for x in rows if x.get("status") == "REJECT"),
                    "fails": sum(1 for x in rows if x.get("status") == "FAIL")},
           "recall_table": table,
           "eviction_probes": [{"tag": p.get("tag"), "doc": p.get("doc_id"), "size": p.get("target_tokens"),
                                "hit_ratio": p.get("hit_ratio"), "cached": p.get("cached_tokens"),
                                "ttft_s": p.get("ttft_s")} for p in probes]}
    with open(os.path.join(rundir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


def selfcheck():
    ok = True

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and cond
    row = blank_row({"doc_id": "X", "phase": "t", "book": "b", "salt": "s", "size": 1, "target_tokens": 1})
    need(all(k in row for k in ("prompt_tokens", "cached_tokens", "ttft_s", "hit_ratio", "reject_reason")),
         "行键集完备律：SKIP 行全键在")
    zh = "第一回 宴桃园豪杰三结义\n" + "好故事。" * 300 + "\n第二回 张翼德怒鞭督邮\n" + "又一章。" * 300
    chs = split_chapters(zh, "zh")
    need(len(chs) == 2 and chs[0][0].startswith("第一回"), f"中文章回切分（{len(chs)}）")
    en = "CHAPTER I.\n\n" + "It was clear. " * 300 + "\n\nCHAPTER II.\n\n" + "Again. " * 300
    ecs = split_chapters(en, "en")
    need(len(ecs) == 2, f"英文章切分（{len(ecs)}）")
    gt = "junk\n*** START OF THE PROJECT GUTENBERG EBOOK X ***\nreal text here\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\ntail junk"
    need(strip_gutenberg(gt).strip().startswith("real text"), "Gutenberg 头尾剥除")
    ps = split_chapters(" ".join(f"para{i} " + "x" * 50 for i in range(400)), "en")
    need(len(ps) > 3, f"伪章回退切片（{len(ps)}）")
    a = SpanAlloc()
    b1 = {"book_id": "b1", "chars": 100000, "chapter_offsets": [0, 20000, 40000, 60000, 80000]}
    s1 = a.take(b1, 15000)
    s2 = a.take(b1, 15000)
    need(s1 and s2 and s2[0] >= s1[1] and s2[1] == 40000, f"章界对齐不相交（{s1},{s2}）")
    need("kv_available_tokens" in MET_KEYS and "num_retracted_reqs" in MET_KEYS, "metrics 键面")
    plan = {"docs": [{"doc_id": "L0001", "target_tokens": 8192}, {"doc_id": "L0002", "target_tokens": 32768},
                     {"doc_id": "M0001", "target_tokens": 524288}], "main_doc_tokens": 524288}
    need(len(pick_hot(plan)) == 3, "热召回取旧三档（8k/32k/主力）")
    print("selfcheck:", "OK" if ok else "NG")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("prep")
    p.add_argument("--raw-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--books", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--pool-tokens", type=int, required=True)
    p.add_argument("--main-doc-tokens", type=int, required=True)
    p.add_argument("--ladder", default="8192,32768,65536,131072,262144,524288")
    p.add_argument("--shots-per-ladder", type=int, default=4)
    p.add_argument("--cpt-zh", type=float, default=1.5)
    p.add_argument("--cpt-en", type=float, default=4.2)
    p.add_argument("--holdout-chars", type=int, default=1500000)
    p.add_argument("--pressure-chars", type=int, default=1200000)
    p.add_argument("--salt-books", type=int, default=6)
    for name in ("fill", "recall", "evict", "calib", "report"):
        p = sub.add_parser(name)
        p.add_argument("--plan", required=True)
        p.add_argument("--rundir", required=True)
        p.add_argument("--model", default="deepseek-v4.1-flash")
        p.add_argument("--base", default="http://127.0.0.1:8898")
        p.add_argument("--gen-tokens", type=int, default=24)
        p.add_argument("--water-abort-m", type=int, default=7168)
        p.add_argument("--http-timeout", type=int, default=5400)
        p.add_argument("--tl-budget", type=int, default=2478000000)
        p.add_argument("--snap-every", type=int, default=10)
        p.add_argument("--rows-name", default="rows.jsonl")
        if name == "fill":
            p.add_argument("--until-pct", type=float, default=None)
            p.add_argument("--limit-per-size", type=int, default=None)
            p.add_argument("--single-above", type=int, default=None)
            p.add_argument("--concurrency", type=int, default=4)
            p.add_argument("--reserve-tokens", type=int, default=200000)
            p.add_argument("--append-salt", action="store_true")
        if name == "recall":
            p.add_argument("--checkpoint", type=int, required=True)
            p.add_argument("--cold-sizes", type=int, nargs="*", default=None)
            p.add_argument("--cold-max-per-size", type=int, default=None)
            p.add_argument("--no-cold", action="store_true")
        if name == "evict":
            p.add_argument("--use-salt", action="store_true")
            p.add_argument("--press-tokens", type=int, default=None)
    args = ap.parse_args()
    if args.selfcheck:
        sys.exit(selfcheck())
    if not args.cmd:
        ap.print_help()
        sys.exit(2)
    fn = {"prep": cmd_prep, "plan": cmd_plan, "fill": cmd_fill, "recall": cmd_recall,
          "evict": cmd_evict, "calib": cmd_calib, "report": cmd_report}[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
