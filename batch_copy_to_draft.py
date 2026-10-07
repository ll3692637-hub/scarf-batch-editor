#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量：日产文案 .md → 公式格子查表取片 → 剪映 5.6 草稿（一条文案一个草稿）

原理（用户 2026-10-05 定，v3 配音驱动语意分段）：
  按「一个完整意思」把文案拆成 5-8 段（每行 ≤16 字、每段 ≤2 行）；
  每段时长按邻居阿姨实测语速（0.244秒/字）预估，字幕=配音=画面三轨对齐；
  第1段→开头文件夹；工艺浓度最高的不超过2段→细节文件夹；
  其余全部→人物文件夹（一条视频最多2个细节镜头，用户定）；
  取片按「用得最少优先」（计数持久化），一条视频内不重用，
  保证所有素材用得均匀、视频之间不像；
  一段一个主镜头；BGM 一条通铺不断；
  草稿不预置配音占位（5.6 不会自动合成），用户在 5.6 全选字幕手动朗读。
  用户只负责按约定整理好素材文件夹。

文件夹约定（Mac）：
  <lib>/<品名>/
    开头/    # 第一段专用
    细节/    # 工艺面料纹理特写
    人物/    # 上身穿戴人物镜头
    氛围/    # 可选；没有或为空则用人物的顶

用法（Mac）：
  python3 batch_copy_to_draft.py --copy copy/2026-10-05-productA.md \\
      --product 产品A --lib ~/Movies/jianying_assets/素材库 \\
      [--bgm ~/Movies/jianying_assets/bgm/xxx.mp3] [--start 1] [--count 20] [--dry-run]

  --dry-run 只打印取片计划，不生成草稿（Linux 也可跑，用于检查解析）

配音（2026-10-05 用户定：真音频直铺，省掉 5.6 手动朗读+回填）：
  --tts doubao  用豆包 Seed-TTS 知性温婉2.0 逐段合成 wav（需 --tts-key 或环境变量 DOUBAO_TTS_KEY）
  --tts edge    用免费 edge-tts（晓晓）逐段合成 mp3
  --tts none    不合成（默认）：按 0.244秒/字预估，5.6 里手动朗读
  合成的音频存 <lib的父目录>/vo/<草稿名>/seg_XX.wav(mp3)，断点续跑自动复用
"""
import argparse, json, os, re, subprocess, sys

# ---------- 公式格子 → 素材文件夹 ----------
# v2（2026-10-05 流沙金规则，用户拍板）：
#   第1句 → 开头文件夹（缺席/为空回退人物）
#   面料工艺 → 细节（工艺面料纹理特写）
#   其余 → 细节/人物交替（避免连续同类，保证画面变化）
# v1 映射保留作参考，见 skill references/batch-copy-to-draft.md
CELL_TO_FOLDER = {
    "面料工艺": "细节", "款式设计": "细节", "颜色": "细节",
    "对比": "细节", "纹样叙事": "细节", "功效性能": "细节", "功效": "细节",
    "人群": "人物", "戴法": "人物", "身份认同": "人物", "趋势风格": "人物",
    "穿着场合": "氛围", "场景": "氛围", "季节": "氛围",
}
FOLDERS = ("细节", "人物", "氛围", "开头")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".MP4", ".MOV")
SEC_PER_CHAR = 0.244  # 邻居阿姨实测语速（edl_to_draft.py）


# ---------- 1. 解析日产文案 md ----------
def parse_copy_md(path):
    """返回 [{idx, formula, hook, text, cells}]"""
    items = []
    cur = None
    body_lines = []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for ln in lines + ["### END"]:
        m = re.match(r"^###\s*(\d+)[｜|](.*)", ln)
        if m:
            if cur:
                cur["text"] = "\n".join(body_lines).strip()
                items.append(cur)
            cur = {"idx": int(m.group(1)), "head": m.group(2).strip(),
                   "formula": "", "hook": "", "text": "", "cells": []}
            body_lines = []
            parts = cur["head"].split("｜")
            if parts:
                cur["formula"] = parts[0].strip()
            if len(parts) > 1:
                cur["hook"] = parts[-1].strip()
            continue
        if cur is None:
            continue
        s = ln.strip()
        if s.startswith("- 格子落点："):
            cell_part = s[len("- 格子落点："):]
            for chunk in re.split(r"[；;]", cell_part):
                if "→" in chunk:
                    cur["cells"].append(chunk.split("→")[0].strip())
            continue
        if s.startswith("- ") or s.startswith("---") or not s:
            continue
        if s.startswith("#"):
            continue
        body_lines.append(s)
    if cur:  # 收录最后一条
        cur["text"] = "\n".join(body_lines).strip()
        if cur["text"]:
            items.append(cur)
    return [it for it in items if it["text"]]


# ---------- 2. 断句 ----------
def split_sentences(text):
    text = re.sub(r"\s+", "", text)
    parts = re.split(r"(?<=[。！？])", text)
    return [p for p in parts if p]


# ---------- 2b. 语意分段（2026-10-05晚 用户定：按完整意思拆 5-8 段） ----------
MAX_LINE_CHARS = 16  # 一行字幕不超 16 字
MAX_SEG_LINES = 2    # 一段最多 2 行（两句短句）
MAX_SEG_CHARS = 30   # 一段不超 30 字

CRAFT_KW = ("拉绒", "面料", "工艺", "桑蚕丝", "纹理", "色织", "流苏",
            "锁边", "绒面", "雾面", "织", "染")

def split_sentence_lines(sentence, max_chars=MAX_LINE_CHARS):
    """一句 → ≤16 字的行：按标点贪心累积；无标点超长才硬切，
    硬切时不把 ，；：、 留成下一行的孤儿。"""
    sentence = sentence.strip()
    if len(sentence) <= max_chars:
        return [sentence]
    parts = re.split(r'(?<=[，；：、])', sentence)
    lines, buf = [], ""
    for p in parts:
        if len(buf + p) <= max_chars:
            buf += p
        else:
            if buf:
                lines.append(buf)
                buf = ""
            while len(p) > max_chars:  # 兜底硬切
                cut = max_chars
                if cut < len(p) and p[cut] in "，；：、":
                    cut += 1  # 切点后是标点就多带一位，不留孤儿
                lines.append(p[:cut])
                p = p[cut:]
            buf = p
    if buf:
        lines.append(buf)
    return [l for l in lines if l]


def _slen(sg):
    return sum(len(x) for x in sg)


# ---------- 3b. 段内轮播短字幕 ----------
CAPTION_MIN, CAPTION_MAX = 8, 14
# 保护词：百分比/尺寸/工艺固定词组，切字幕时不拆开
_CAPTION_PROT_RE = re.compile(r"\d+%\S*?(?=[，；：、！？。\s]|$)|\d+×\d+")
_CAPTION_PROT_WORDS = ("桑蚕丝", "色织提花", "双面提花", "双面异色", "非遗拉绒",
                       "真丝拉绒", "手工抽须", "无痕锁边", "低温微熔")


def _caption_spans(text):
    spans = [(m.start(), m.end()) for m in _CAPTION_PROT_RE.finditer(text)]
    for w in _CAPTION_PROT_WORDS:
        i = 0
        while True:
            j = text.find(w, i)
            if j < 0:
                break
            spans.append((j, j + len(w)))
            i = j + 1
    return spans


def _strip_cap(s):
    return s.strip().rstrip("，、；：。！？")


_CONN_RE = re.compile(r"然而|但是|而且|所以|因为|不是|就是|如果|又|但|而")


def _in_span(p, spans):
    return any(s < p < e for s, e in spans)


def _caption_cut(text, pos, n, spans):
    """找最佳切点（两轮）：
    第一轮：窗内自然切点（标点 > 连接词前 > 保护词前），本条 ≥8 字；
    第二轮：同上放宽到 ≥6 字（不断碎尾）；
    都没有 → 硬切 14（不进保护词）；尾巴 <6 字则直接收到尾。"""
    limit = min(pos + CAPTION_MAX, n)

    def natural_cands(min_len):
        cands = set()
        for m in re.finditer(r"[，；：、！？。]", text[pos:limit]):
            cands.add(pos + m.end())                       # 窗内标点
        for m in _CONN_RE.finditer(text[pos:limit]):
            cands.add(pos + m.start())                     # 窗内连接词前
        for s, e in spans:
            if pos < s < limit:
                cands.add(s)                                # 保护词前
        cands.discard(n)  # n 只做最后兜底
        out = []
        for cut in sorted(cands, reverse=True):
            if cut <= pos or cut > n:
                continue
            if _in_span(cut, spans):
                continue                                    # 不在保护词中间切
            if cut - pos < min_len:
                continue
            if 0 < n - cut < 6:
                continue                                    # 不留短尾
            out.append(cut)
        return out

    for min_len in (CAPTION_MIN, 6):
        cands = natural_cands(min_len)
        if cands:
            return cands[0]
    # 停顿只差一点：两轮都无自然切点时，才顺延窗外 +4 字内的标点
    # （如"，每年给闺蜜挑生日礼物都纠结的人，" 的逗号刚好在窗外）
    m2 = re.search(r"[，；：、！？。]", text[limit:limit + 4])
    if m2:
        cut = limit + m2.end()
        if cut - pos <= 18 and not _in_span(cut, spans):
            return n if 0 < n - cut < 6 else cut
    # 硬切
    cut = limit
    if _in_span(cut, spans):
        for s, e in spans:
            if s < cut < e:
                cut = s if s - pos >= 6 else e
                break
    if 0 < n - cut < 6:
        cut = n
    return cut if cut > pos else n


def split_captions(narr):
    """配音文案 → 段内轮播短字幕：8–14字，自然停顿处切，不拆保护词。
    尾随标点去掉（轮播小字幕不带逗号句号）；时长按字数比例分（edl_to_draft 侧做）。"""
    text = narr.replace("\n", "").strip()
    n = len(text)
    if n == 0:
        return []
    if n <= CAPTION_MAX:
        return [_strip_cap(text)]
    spans = _caption_spans(text)
    caps, pos = [], 0
    while pos < n:
        cut = _caption_cut(text, pos, n, spans)
        cap = _strip_cap(text[pos:cut])
        if cap:
            caps.append(cap)
        pos = cut if cut > pos else pos + 1  # 保险：防止死循环
    return caps


def _sentence_pieces(sentence):
    """一句 → [(lines, is_whole)]。
    先按 ；： 切分句读（强边界）：分句读完整就不断；
    整句 ≤2 行 → 一整块；超长（分句读）按 2 行切块。
    只有"单分句读且≤2行"才算整句（可参与跨句合并）。"""
    clauses = [c for c in re.split(r"(?<=[；：])", sentence.strip()) if c]
    clause_lines = [split_sentence_lines(c) for c in clauses]
    if len(clauses) == 1 and len(clause_lines[0]) <= MAX_SEG_LINES:
        return [(clause_lines[0], True)]
    pieces, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            pieces.append((cur, False))
            cur = []

    for cl in clause_lines:
        if len(cl) > MAX_SEG_LINES:
            flush()
            # 超长分句读按 2 行切；尾块若是 1 行逗号行则并回前块
            chunks = [cl[k:k + MAX_SEG_LINES]
                      for k in range(0, len(cl), MAX_SEG_LINES)]
            if (len(chunks) > 1 and len(chunks[-1]) == 1
                    and chunks[-1][0][-1] in "，、"):
                chunks[-2] = chunks[-2] + chunks[-1]
                chunks.pop()
            for ch in chunks:
                pieces.append((ch, False))
        elif len(cur) + len(cl) <= MAX_SEG_LINES:
            cur.extend(cl)
        else:
            flush()
            cur = list(cl)
    flush()
    return pieces


def build_segments(text):
    """v7.2（2026-10-05）：句子完整优先，专治"断句不对"。
    - 长句按强标点（；：）拆分句读再打包，不拦腰切；
    - 每段 ≤2 行；单行段必以 。！？；： 结尾，逗号结尾必为 2 行；
    - 整句之间尽量合并（≤2行、≤30字），碎块不参与合并；
    - 不断句、不出单个逗号短句、不出 3 行段。"""
    pieces = []
    for s in split_sentences(text):
        pieces.extend(_sentence_pieces(s))

    segs, cur, cur_whole = [], [], True

    def cur_chars():
        return sum(len(x) for x in cur)

    def flush():
        nonlocal cur, cur_whole
        if cur:
            segs.append(list(cur))
        cur, cur_whole = [], True

    for lines, whole in pieces:
        if (cur and cur_whole and whole
                and len(cur) + len(lines) <= MAX_SEG_LINES
                and cur_chars() + sum(len(x) for x in lines) <= MAX_SEG_CHARS):
            cur.extend(lines)
        else:
            flush()
            cur.extend(lines)
            cur_whole = whole
    flush()

    # 超过 8 段：合并总字数最小的相邻整句对（都以 。！？ 结尾才并）
    def _ends(sg):
        return "".join(sg)[-1] in "。！？"

    while len(segs) > 8:
        best, best_n = None, None
        for k in range(len(segs) - 1):
            if not (_ends(segs[k]) and _ends(segs[k + 1])):
                continue
            merged = segs[k] + segs[k + 1]
            if len(merged) <= MAX_SEG_LINES and _slen(merged) <= MAX_SEG_CHARS:
                n = _slen(merged)
                if best_n is None or n < best_n:
                    best, best_n = k, n
        if best is None:
            break
        segs[best] = segs[best] + segs[best + 1]
        del segs[best + 1]
    return segs


def seg_duration(seg):
    """配音驱动：按实测语速预估本段时长（秒），字幕=配音=画面共用。
    --tts doubao/edge 时会被真实音频时长覆盖。"""
    n = sum(len(l) for l in seg)
    return round(max(1.2, n * SEC_PER_CHAR), 1)
def assign_folders(segments):
    """v4（2026-10-05）：第1段→开头；工艺浓度最高的不超过2段→细节；其余→人物。
    一条视频最多2个细节镜头，其余全部人物（用户定）。"""
    n = len(segments)
    res = ["人物"] * n
    if n:
        res[0] = "开头"
    scored = []
    for i in range(1, n):
        text = "".join(segments[i])
        score = sum(text.count(k) for k in CRAFT_KW)
        scored.append((score, i))
    scored.sort(key=lambda x: (-x[0], x[1]))  # 工艺浓度优先，相同早段优先
    detail_n = 0
    for score, i in scored:
        if score > 0 and detail_n < 2:
            res[i] = "细节"
            detail_n += 1
    return res


# ---------- 4. 文件夹轮询取片（状态持久化，保证 20 条不重样） ----------
MIN_SLOWMO_RATE = 0.5  # 慢放下限：低于此倍率宁可换素材


def probe_duration(path):
    """ffprobe 读时长（秒），失败返回 0。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path], capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


class ClipPicker:
    def __init__(self, product_dir):
        self.product_dir = product_dir
        self.state_path = os.path.join(product_dir, ".picker_state.json")
        self.state = {}
        if os.path.isfile(self.state_path):
            try:
                self.state = json.load(open(self.state_path, encoding="utf-8"))
            except Exception:
                self.state = {}
        self.clips = {}
        for folder in FOLDERS:
            d = os.path.join(product_dir, folder)
            if os.path.isdir(d):
                self.clips[folder] = sorted(
                    os.path.join(d, f) for f in os.listdir(d)
                    if f.endswith(VIDEO_EXTS) and not f.startswith("."))
            else:
                self.clips[folder] = []
        # 素材时长缓存（mtime 变化才重探）
        self.dur_path = os.path.join(product_dir, ".clip_durations.json")
        self.durations = {}
        if os.path.isfile(self.dur_path):
            try:
                self.durations = json.load(open(self.dur_path, encoding="utf-8"))
            except Exception:
                self.durations = {}
        self._pair_rate = None  # 上一段被慢放 → 下一段强制同倍率（配对）

    def duration(self, clip):
        try:
            mt = os.path.getmtime(clip)
        except OSError:
            return 0.0
        rec = self.durations.get(clip)
        if isinstance(rec, list) and rec[0] == mt:
            return rec[1]
        d = probe_duration(clip)
        self.durations[clip] = [mt, d]
        return d

    def _counts(self, folder):
        st = self.state.get(folder)
        if isinstance(st, dict):
            return st.get("counts", {})
        return {}  # 旧版 state 是 {folder: int}，直接从零开始计数

    def _bump(self, folder, clip):
        counts = self._counts(folder)
        counts[clip] = counts.get(clip, 0) + 1
        self.state[folder] = {"counts": counts}

    def pick(self, folder, target_dur, exclude=None):
        """均衡取片 v2：
        - 使用次数最少优先；次数相同时选时长最接近目标段落的（短素材配短段）；
        - 素材不够长可慢放，但倍率不低于 0.5，否则换下一个；
        - 某段被慢放 → 紧接下一段强制同倍率（配对），之后恢复正常；
        - 短素材不排除在轮换池外，也不用长素材硬顶短段。"""
        exclude = exclude or set()
        if folder == "氛围" and not self.clips.get("氛围"):
            folder = "人物"  # 氛围缺席用人物的顶
        if folder == "开头" and not self.clips.get("开头"):
            folder = "人物"  # 开头缺席用人物的顶
        pool = self.clips.get(folder, [])
        if not pool:
            raise SystemExit(
                f"❌ 文件夹缺素材：{os.path.join(self.product_dir, folder)}\n"
                f"   请先把该品的「{folder}」素材整理好再跑批量。")
        counts = self._counts(folder)
        # 按文件名去重：同一素材可能分在多个文件夹（如开头/人物都有 C2762.MP4），
        # 只比完整路径会漏过去，一条视频内视觉上就重复了
        cands = [c for c in pool if os.path.basename(c) not in exclude]
        if not cands:
            print(f"  ⚠️ 「{folder}」素材不够分，本条复用片段")
            cands = list(pool)

        if self._pair_rate is not None:
            # 配对段：强制同倍率，保证衔接运动节奏一致
            r = self._pair_rate
            self._pair_rate = None
            need = r * target_dur
            ordered = sorted(cands,
                             key=lambda c: (counts.get(c, 0),
                                            abs(self.duration(c) - need)))
            chosen = next((c for c in ordered if self.duration(c) >= need),
                          ordered[0])
            self._bump(folder, chosen)
            print(f"  取片[{folder}] {os.path.basename(chosen)}（配对慢放 {r:.2f}x）")
            return chosen, r

        ordered = sorted(
            cands, key=lambda c: (counts.get(c, 0), abs(self.duration(c) - target_dur)))
        for c in ordered:
            d = self.duration(c)
            rate = 1.0 if d >= target_dur or target_dur <= 0 else d / target_dur
            if rate < MIN_SLOWMO_RATE:
                continue  # 太短了，慢放会过慢，换下一个
            self._bump(folder, c)
            if rate < 1.0 - 1e-9:
                self._pair_rate = rate  # 下一段配对同倍率
                print(f"  取片[{folder}] {os.path.basename(c)}"
                      f"（{d:.1f}s→{target_dur:.1f}s，{rate:.2f}x 慢放，下一段配对）")
            return c, rate
        # 兜底：都太短，选使用最少/时长最接近的，edl 侧告警
        c = ordered[0]
        d = self.duration(c)
        rate = max(d / target_dur, 0.3) if target_dur > 0 else 1.0
        self._bump(folder, c)
        print(f"  ⚠️ 「{folder}」素材都偏短，{os.path.basename(c)} 将 {rate:.2f}x 慢放（低于下限）")
        return c, rate

    def save(self):
        json.dump(self.state, open(self.state_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        try:
            json.dump(self.durations, open(self.dur_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass


# ---------- 5b. 真音频合成（2026-10-05 用户定：配音轨直铺，省朗读+回填） ----------
def wav_duration(path):
    """读音频时长（秒），ffprobe 方案，mp3/wav 通用。"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True, timeout=20)
    return float(r.stdout.strip())


def _seg_tag(narr, voice=""):
    import hashlib
    return hashlib.md5(f"{voice}|{narr}".encode("utf-8")).hexdigest()[:8]


def synth_segments_tts(segs, draft_name, a):
    """逐段合成真音频 → seg["audio"]=路径、seg["out"]=真实时长。
    音频存 <lib父目录>/vo/<草稿名>/seg_XX.*，已存在的直接复用（断点续跑）。"""
    provider = a.tts
    vo_root = os.path.join(
        os.path.dirname(os.path.abspath(os.path.expanduser(a.lib))), "vo")
    vo_dir = os.path.join(vo_root, draft_name)
    os.makedirs(vo_dir, exist_ok=True)

    if provider == "doubao":
        key = a.tts_key or os.environ.get("DOUBAO_TTS_KEY", "")
        if not key:
            sys.exit("❌ --tts doubao 需要 key：--tts-key KEY 或 export DOUBAO_TTS_KEY='...'（推荐后者，不落 shell 历史）")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import tts_doubao
        voice = a.tts_voice or tts_doubao.DEFAULT_SPEAKER
        print(f"  配音：豆包 {voice}")
        for k, s in enumerate(segs):
            out = os.path.join(vo_dir, f"seg_{k:02d}_{_seg_tag(s['narr'], voice)}.wav")
            if os.path.isfile(out):
                dur = wav_duration(out)
                print(f"  配音{k+1}: 复用 {dur:.1f}s")
            else:
                try:
                    dur = tts_doubao.synth(
                        s["narr"], out, key, voice, a.tts_resource, a.tts_rate)
                except tts_doubao.TtsError as e:
                    sys.exit(f"❌ 第{k+1}段合成失败：{e}\n   已合成的音频保留在 {vo_dir}，修好 key 后重跑自动续上")
                print(f"  配音{k+1}: {dur:.1f}s")
            s["audio"] = out
            s["out"] = round(s["in"] + dur, 2)
    elif provider == "edge":
        voice = a.tts_voice or "zh-CN-XiaoxiaoNeural"
        print(f"  配音：edge-tts {voice}（免费）")
        for k, s in enumerate(segs):
            out = os.path.join(vo_dir, f"seg_{k:02d}_{_seg_tag(s['narr'], voice)}.mp3")
            if os.path.isfile(out):
                dur = wav_duration(out)
                print(f"  配音{k+1}: 复用 {dur:.1f}s")
            else:
                cmd = [sys.executable, "-m", "edge_tts", "-t", s["narr"],
                       "-v", voice, "--write-media", out]
                if a.tts_rate:
                    cmd.append(f"--rate={a.tts_rate:+d}%")
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode != 0 or not os.path.isfile(out):
                    sys.exit(f"❌ 第{k+1}段合成失败：{r.stderr.strip()[:200]}\n"
                             f"   先确认本机能跑通：python3 -m edge_tts -t 你好 -v {voice} --write-media /tmp/t.mp3")
                dur = wav_duration(out)
                print(f"  配音{k+1}: {dur:.1f}s")
            s["audio"] = out
            s["out"] = round(s["in"] + dur, 2)
    return segs


# ---------- 5. 组 EDL（语意段：文案 / 配音时长 / 素材 / 入出点 / 轮播字幕） ----------
def build_edl(item, picker, draft_name, voice, bgm, a=None):
    segments = build_segments(item["text"])
    folders = assign_folders(segments)
    segs = []
    for seg_lines in segments:
        narr = "\n".join(seg_lines)
        dur = seg_duration(seg_lines)  # 预估；真音频会覆盖
        segs.append({"narr": narr, "in": 0, "out": dur,
                     "captions": split_captions(narr)})
    if a is not None and a.tts != "none":
        synth_segments_tts(segs, draft_name, a)  # 真音频覆盖 out 时长
    # 取片：用真实时长做时长分层（短素材配短段），慢放配对由 picker 决定
    used = set()  # 本条内不重用片段（存文件名：同一素材可能分在多个文件夹）
    for s, folder in zip(segs, folders):
        target_dur = s["out"] - s["in"]
        clip, rate = picker.pick(folder, target_dur, exclude=used)
        used.add(os.path.basename(clip))
        s["clip"] = clip
        s["_folder"] = folder
        if rate < 1.0 - 1e-9:
            s["slowmo"] = round(rate, 3)
    edl = {"draft_name": draft_name, "segments": segs,
           "tts_voice": voice, "width": 1080, "height": 1920, "fps": 30}
    if bgm:
        edl["bgm"] = bgm
        edl["bgm_volume"] = 0.15
    return edl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", required=True, help="日产文案 md 路径")
    ap.add_argument("--product", required=True, help="品名（= 素材库子文件夹名）")
    ap.add_argument("--lib", required=True, help="素材库根目录")
    ap.add_argument("--bgm", default="", help="BGM 本地 mp3（可选）")
    ap.add_argument("--voice", default="jianying:邻居阿姨")
    ap.add_argument("--tts", default="none", choices=["none", "edge", "doubao"],
                    help="配音：none=预估时长+5.6手动朗读；edge=免费晓晓；doubao=豆包直铺")
    ap.add_argument("--tts-key", default="",
                    help="豆包 API Key（或环境变量 DOUBAO_TTS_KEY，推荐）")
    ap.add_argument("--tts-voice", default="",
                    help="覆盖默认音色（doubao 默认知性灿灿2.0；edge 默认 zh-CN-XiaoxiaoNeural）")
    ap.add_argument("--tts-resource", default="seed-tts-2.0")
    ap.add_argument("--tts-rate", type=int, default=0,
                    help="语速 -50~100，0=正常")
    ap.add_argument("--start", type=int, default=1, help="从第几条开始")
    ap.add_argument("--count", type=int, default=0, help="跑几条（0=全部）")
    ap.add_argument("--random", type=int, default=0,
                    help="随机抽 N 条文案（与 --start/--count 互斥）")
    ap.add_argument("--seed", type=int, default=0,
                    help="随机种子（0=真随机；给种子可复现抽到的条目）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划")
    a = ap.parse_args()

    items = parse_copy_md(a.copy)
    if not items:
        print("❌ 文案文件里没解析出条目"); sys.exit(1)
    print(f"解析出 {len(items)} 条文案")

    # 日期后缀：从文件名取 2026-10-05 → 1005
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(a.copy))
    date_tag = f"{m.group(2)}{m.group(3)}" if m else "0000"

    product_dir = os.path.join(os.path.expanduser(a.lib), a.product)
    picker = ClipPicker(product_dir)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    gen = os.path.join(script_dir, "edl_to_draft.py")

    targets = items[a.start - 1:]
    if a.count:
        targets = targets[:a.count]
    if a.random:
        import random as _random
        rng = _random.Random(a.seed) if a.seed else _random.SystemRandom()
        targets = rng.sample(items, min(a.random, len(items)))
        print(f"随机抽 {len(targets)} 条："
              + "、".join(f"#{items.index(t)+1}" for t in targets)
              + (f"（seed={a.seed}）" if a.seed else ""))

    for it in targets:
        draft_name = f"{a.product}_{date_tag}_{it['idx']:02d}"
        if a.dry_run:
            segments = build_segments(it["text"])
            folders = assign_folders(segments)
            print(f"\n[{draft_name}] {it['formula']}｜{it['hook']}")
            used = set()
            total = 0.0
            for k, (seg_lines, f) in enumerate(zip(segments, folders)):
                dur = seg_duration(seg_lines)
                clip, rate = picker.pick(f, dur, exclude=used)
                used.add(os.path.basename(clip))
                total += dur
                nchars = sum(len(l) for l in seg_lines)
                txt = " / ".join(seg_lines)
                caps = split_captions("\n".join(seg_lines))
                slow = f" {rate:.2f}x慢放" if rate < 1.0 - 1e-9 else ""
                print(f"  段{k+1} [{f}] {txt[:26]}"
                      f"（{nchars}字≈{dur}s 配音时长）← {os.path.basename(clip)}{slow}")
                print(f"      轮播字幕：{' ｜ '.join(caps)}")
            print(f"  共 {len(segments)} 段，总约 {round(total, 1)}s")
            continue
        edl = build_edl(it, picker, draft_name, a.voice, a.bgm or "", a)
        edl_path = f"/tmp/batch_edl_{it['idx']:02d}.json"
        json.dump({k: v for k, v in edl.items()},
                  open(edl_path, "w", encoding="utf-8"), ensure_ascii=False)
        # 去掉内部 _folder 标记再喂给 edl_to_draft
        clean = json.load(open(edl_path, encoding="utf-8"))
        for s in clean["segments"]:
            s.pop("_folder", None)
        json.dump(clean, open(edl_path, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"\n=== [{draft_name}] 生成草稿 ===")
        r = subprocess.run([sys.executable, gen, edl_path])
        if r.returncode != 0:
            print(f"❌ {draft_name} 失败，停在第 {it['idx']} 条")
            picker.save()
            sys.exit(1)
        picker.save()

    if a.dry_run:
        print("\n(dry-run，未生成草稿)")
    else:
        print(f"\n✅ 批量完成：{len(targets)} 个草稿已生成，去 5.6 里审核导出")
        if a.tts != "none":
            print("   配音已按真音频铺好，三轨对齐，无需手动朗读/回填")


if __name__ == "__main__":
    main()
