#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 5.6 里实际朗读出的配音时长，回填字幕和画面的时长（三轨严格对齐）。

工作流：
  1. batch_copy_to_draft.py 生成草稿（时长按 0.244秒/字 预估）
  2. 在 5.6 里全选字幕 → 朗读（邻居阿姨）
  3. 彻底退出剪映（Cmd+Q）
  4. python3 retime_to_vo.py 草稿名     ← 本脚本
  5. 重开 5.6 检查导出

原理：朗读后每段配音的 audio material 自带 text_id（指向字幕），
脚本按 text_id 配对，把字幕段和视频段的目标时长改成实际配音时长，
整体 ripple 前移，BGM 保持一条通铺。
没朗读的段保持原时长不动。
"""
import json
import os
import shutil
import sys
import time


def find_draft_root():
    home = os.path.expanduser("~")
    p = os.path.join(home, "Movies", "JianyingPro", "User Data",
                     "Projects", "com.lveditor.draft")
    return p if os.path.isdir(p) else None


def main():
    if sys.platform != "darwin":
        print("只支持 macOS")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("用法: python3 retime_to_vo.py 草稿名")
        sys.exit(1)
    name = sys.argv[1]

    root = find_draft_root()
    if not root:
        print("❌ 没找到草稿目录")
        sys.exit(1)
    target = os.path.join(root, name)
    info_path = os.path.join(target, "draft_info.json")
    if not os.path.isfile(info_path):
        print(f"❌ 没找到草稿: {name}")
        sys.exit(1)

    info = json.load(open(info_path, encoding="utf-8"))
    mats = info.get("materials", {})
    audios = mats.get("audios", [])
    mat_by_id = {a["id"]: a for a in audios}
    mat_by_id.update({v["id"]: v for v in mats.get("videos", [])})
    speeds_by_id = {s["id"]: s for s in mats.get("speeds", [])}

    tracks = info.get("tracks", [])
    vtrs = [t for t in tracks if t.get("type") == "video"]
    ttrs = [t for t in tracks if t.get("type") == "text"]
    atrs = [t for t in tracks if t.get("type") == "audio"]
    if not vtrs or not ttrs:
        print("❌ 草稿里没找到视频/字幕轨")
        sys.exit(1)

    def is_vo_track(tr):
        for s in tr.get("segments", []):
            m = mat_by_id.get(s.get("material_id"))
            if m and m.get("text_id"):
                return True
        return False

    vo_tracks = [t for t in atrs if is_vo_track(t)]
    bgm_tracks = [t for t in atrs if not is_vo_track(t)]

    vsegs = sorted(vtrs[0].get("segments", []),
                   key=lambda s: s["target_timerange"]["start"])
    tsegs = sorted(ttrs[0].get("segments", []),
                   key=lambda s: s["target_timerange"]["start"])
    n = min(len(vsegs), len(tsegs))
    if len(vsegs) != len(tsegs):
        print(f"  ⚠️ 视频段 {len(vsegs)} ≠ 字幕段 {len(tsegs)}，按前 {n} 段配对")

    # 配音段：先按 text_id 配对，配不上则按顺序兜底
    vo_segs = []
    for tr in vo_tracks:
        vo_segs.extend(tr.get("segments", []))
    vo_segs.sort(key=lambda s: s["target_timerange"]["start"])

    vo_dur_by_tid = {}
    for s in vo_segs:
        m = mat_by_id.get(s.get("material_id"))
        if m and m.get("text_id"):
            vo_dur_by_tid[m["text_id"]] = s["target_timerange"]["duration"]

    new_durs, src_note = [], []
    for i in range(n):
        tid = tsegs[i]["material_id"]
        d = vo_dur_by_tid.get(tid)
        if d is None and vo_segs and len(vo_segs) >= n:
            d = vo_segs[i]["target_timerange"]["duration"]  # 顺序兜底
        old = tsegs[i]["target_timerange"]["duration"]
        new_durs.append(d or old)
        src_note.append("配音" if d else "保持")

    if not any(vo_dur_by_tid.values()) and not vo_segs:
        print("❌ 草稿里没找到朗读生成的配音：先在 5.6 里全选字幕点朗读，再退出剪映跑本脚本")
        sys.exit(1)

    # 回填：字幕 & 视频目标时长 = 实际配音时长；视频源时长相应收缩/拉伸
    cursor = 0
    for i in range(n):
        d = new_durs[i]
        old = tsegs[i]["target_timerange"]["duration"]
        tsegs[i]["target_timerange"]["start"] = cursor
        tsegs[i]["target_timerange"]["duration"] = d
        vs = vsegs[i]
        factor = vs.get("speed", 1.0) or 1.0
        vm = mat_by_id.get(vs.get("material_id"))
        src_start = vs["source_timerange"]["start"]
        avail = (vm["duration"] - src_start) if vm else d * 2
        need = int(d * factor)
        if need > avail:
            factor = avail / d
            need = avail
            vs["speed"] = factor
            for mid in vs.get("extra_material_refs", []):
                sp = speeds_by_id.get(mid)
                if sp:
                    sp["speed"] = factor
        vs["source_timerange"]["duration"] = need
        vs["target_timerange"]["start"] = cursor
        vs["target_timerange"]["duration"] = d
        print(f"  段{i+1}: {old/1e6:.2f}s → {d/1e6:.2f}s（{src_note[i]}）")
        cursor += d
    total = cursor

    # 配音轨：按配对同步起点/时长
    for i in range(n):
        tid = tsegs[i]["material_id"]
        st = tsegs[i]["target_timerange"]["start"]
        d = tsegs[i]["target_timerange"]["duration"]
        for s in vo_segs:
            m = mat_by_id.get(s.get("material_id"))
            hit = (m and m.get("text_id") == tid)
            if not hit and not vo_dur_by_tid and len(vo_segs) >= n and vo_segs[i] is s:
                hit = True  # 顺序兜底
            if hit:
                s["target_timerange"]["start"] = st
                s["target_timerange"]["duration"] = d

    # BGM：保持一条通铺，时长 = min(原BGM, 新总时长)
    for tr in bgm_tracks:
        for s in tr.get("segments", []):
            m = mat_by_id.get(s.get("material_id"))
            full = m.get("duration") if m else s["source_timerange"]["duration"]
            t = min(full, total)
            s["source_timerange"] = {"start": 0, "duration": t}
            s["target_timerange"] = {"start": 0, "duration": t}

    info["duration"] = total
    info["update_time"] = int(time.time() * 1_000_000)
    shutil.copy2(info_path, info_path + ".retime_bak")
    json.dump(info, open(info_path, "w", encoding="utf-8"), ensure_ascii=False)

    meta_path = os.path.join(target, "draft_meta_info.json")
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path, encoding="utf-8"))
        meta["tm_draft_modified"] = info["update_time"]
        meta["tm_duration"] = total
        meta["draft_timeline_materials_size_"] = os.path.getsize(info_path)
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False)

    locked = os.path.join(target, ".locked")
    if os.path.exists(locked):
        os.remove(locked)

    print(f"\n✅ 回填完成：{n} 段，总 {total/1e6:.1f}s。重开 5.6 检查导出")


if __name__ == "__main__":
    main()
