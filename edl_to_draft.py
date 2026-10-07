#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EDL -> 剪映 5.6 草稿生成器 v1.1
用法：
    python3 edl_to_draft.py edl.json
EDL 格式见 references/edl-spec.md（v2.0）
前置：剪映 5.6 已创建空白草稿 TEMPLATE，且已彻底退出（Cmd+Q）

配音两种模式：
  1. EDL 每段带 "audio": wav路径 → 用真实音频时长驱动，铺真配音轨，
     字幕=配音=画面三轨严格对齐（batch 用 --tts doubao/edge 时走这个）
  2. 不带 audio → 按 in/out 预估时长（旧流程），需在 5.6 手动朗读+回填
"""
import copy, json, os, re, shutil, subprocess, sys, time, uuid

REF_STRUCTS = json.loads('{"video_mat": {"aigc_type": "none", "audio_fade": null, "cartoon_path": "", "category_id": "", "category_name": "local", "check_flag": 63487, "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0}, "crop_ratio": "free", "crop_scale": 1.0, "duration": 10000000, "extra_type_option": 0, "formula_id": "", "freeze": null, "gameplay": null, "has_audio": true, "height": 1248, "id": "A608702F-9DF9-4298-B047-904DC3D25740", "intensifies_audio_path": "", "intensifies_path": "", "is_ai_generate_content": false, "is_copyright": false, "is_unified_beauty_mode": false, "local_id": "", "local_material_id": "6d174c4b-21ef-4d5c-83f1-e658dd1bed7b", "material_id": "", "material_name": "示例素材.mp4", "material_url": "", "matting": {"flag": 0, "has_use_quick_brush": false, "has_use_quick_eraser": false, "interactiveTime": [], "path": "", "strokes": []}, "media_path": "", "object_locked": null, "origin_material_id": "", "path": "/path/to/your/clip.mp4", "picture_from": "none", "picture_set_category_id": "", "picture_set_category_name": "", "request_id": "", "reverse_intensifies_path": "", "reverse_path": "", "smart_motion": null, "source": 0, "source_platform": 0, "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}}, "team_id": "", "type": "video", "video_algorithm": {"algorithms": [], "deflicker": null, "motion_blur_config": null, "noise_reduction": null, "path": "", "quality_enhance": null, "time_range": null}, "width": 704}, "text_mat": {"add_type": 0, "alignment": 1, "background_alpha": 1.0, "background_color": "", "background_height": 0.14, "background_horizontal_offset": 0.0, "background_round_radius": 0.0, "background_style": 0, "background_vertical_offset": 0.0, "background_width": 0.14, "bold_width": 0.0, "border_alpha": 1.0, "border_color": "", "border_width": 0.08, "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "request_id": "", "resource_id": "", "resource_name": ""}, "check_flag": 7, "combo_info": {"text_templates": []}, "content": "{\\"styles\\":[{\\"fill\\":{\\"content\\":{\\"solid\\":{\\"color\\":[1,1,1]}}},\\"range\\":[0,4],\\"size\\":15,\\"font\\":{\\"path\\":\\"/Applications/VideoFusion-macOS.app/Contents/Resources/Font/SystemFont/zh-hans.ttf\\",\\"id\\":\\"\\"}}],\\"text\\":\\"测试字幕\\"}", "fixed_height": -1.0, "fixed_width": -1.0, "font_category_id": "", "font_category_name": "", "font_id": "", "font_name": "", "font_path": "/Applications/VideoFusion-macOS.app/Contents/Resources/Font/SystemFont/zh-hans.ttf", "font_resource_id": "", "font_size": 15.0, "font_source_platform": 0, "font_team_id": "", "font_title": "none", "font_url": "", "fonts": [], "force_apply_line_max_width": false, "global_alpha": 1.0, "group_id": "", "has_shadow": false, "id": "1455135C-C554-41C0-9C01-0FCFD7F96DCD", "initial_scale": 1.0, "inner_padding": -1.0, "is_rich_text": false, "italic_degree": 0, "ktv_color": "", "language": "", "layer_weight": 1, "letter_spacing": 0.0, "line_feed": 1, "line_max_width": 0.82, "line_spacing": 0.02, "multi_language_current": "none", "name": "", "original_size": [], "preset_category": "", "preset_category_id": "", "preset_has_set_alignment": false, "preset_id": "", "preset_index": 0, "preset_name": "", "recognize_task_id": "", "recognize_type": 0, "relevance_segment": [], "shadow_alpha": 0.8, "shadow_angle": -45.0, "shadow_color": "", "shadow_distance": 8.0, "shadow_point": {"x": 1.0182337649086284, "y": -1.0182337649086284}, "shadow_smoothing": 1.0, "shape_clip_x": false, "shape_clip_y": false, "style_name": "", "sub_type": 0, "subtitle_keywords": null, "subtitle_template_original_fontsize": 0.0, "text_alpha": 1.0, "text_color": "#FFFFFF", "text_curve": null, "text_preset_resource_id": "", "text_size": 30, "text_to_audio_ids": [], "tts_auto_update": false, "type": "text", "typesetting": 0, "underline": false, "underline_offset": 0.22, "underline_width": 0.05, "use_effect_default_color": true, "words": {"end_time": [], "start_time": [], "text": []}}, "speed": {"curve_speed": null, "id": "07B8022A-E4EE-4EB3-9910-29EC105D193D", "mode": 0, "speed": 1.0, "type": "speed"}, "canvas": {"album_image": "", "blur": 0.0, "color": "", "id": "97719EA5-F9B6-4A66-AAD4-34A31FF2A1F7", "image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": "", "type": "canvas_color"}, "video_track": {"attribute": 0, "flag": 0, "id": "493D079D-F197-43C9-97EC-5B1FFDF95FCC", "is_default_name": true, "name": "", "segments": [{"cartoon": false, "clip": {"alpha": 1.0, "flip": {"horizontal": false, "vertical": false}, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}}, "common_keyframes": [], "enable_adjust": true, "enable_color_curves": true, "enable_color_match_adjust": false, "enable_color_wheels": true, "enable_lut": true, "enable_smart_color_adjust": false, "extra_material_refs": ["07B8022A-E4EE-4EB3-9910-29EC105D193D", "97719EA5-F9B6-4A66-AAD4-34A31FF2A1F7", "450A7D8B-647F-41D0-B2D9-BA631EA19410", "8766E172-B497-4DEE-8C7A-C702BC1BFDFF"], "group_id": "", "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000}, "id": "6A899D5E-4F5F-4494-AAE0-CFF1BC695A70", "intensifies_audio": false, "is_placeholder": false, "is_tone_modify": false, "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": "A608702F-9DF9-4298-B047-904DC3D25740", "render_index": 0, "responsive_layout": {"enable": false, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0}, "reverse": false, "source_timerange": {"duration": 10000000, "start": 0}, "speed": 1.0, "target_timerange": {"duration": 10000000, "start": 0}, "template_id": "", "template_scene": "default", "track_attribute": 0, "track_render_index": 0, "uniform_scale": {"on": true, "value": 1.0}, "visible": true, "volume": 1.0}], "type": "video"}, "text_track": {"attribute": 0, "flag": 0, "id": "3518055F-9B39-4DC5-9069-4BC157A4BFD7", "is_default_name": true, "name": "", "segments": [{"cartoon": false, "clip": {"alpha": 1.0, "flip": {"horizontal": false, "vertical": false}, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}}, "common_keyframes": [], "enable_adjust": false, "enable_color_curves": true, "enable_color_match_adjust": false, "enable_color_wheels": true, "enable_lut": false, "enable_smart_color_adjust": false, "extra_material_refs": [], "group_id": "", "hdr_settings": null, "id": "F842C47B-FC6C-46FA-BA5F-270488020C87", "intensifies_audio": false, "is_placeholder": false, "is_tone_modify": false, "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": "00000000-0000-0000-0000-000000000000", "render_index": 14000, "responsive_layout": {"enable": false, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0}, "reverse": false, "source_timerange": null, "speed": 1.0, "target_timerange": {"duration": 10000000, "start": 0}, "template_id": "", "template_scene": "default", "track_attribute": 0, "track_render_index": 1, "uniform_scale": {"on": true, "value": 1.0}, "visible": true, "volume": 1.0}], "type": "text"}, "audio_mat": {"app_id": 0, "category_id": "", "category_name": "", "check_flag": 1, "duration": 3100000, "effect_id": "", "formula_id": "", "id": "AB9F09F9-221F-47A3-B3D5-76A994EDA753", "intensifies_path": "", "is_ai_clone_tone": false, "is_ugc": false, "local_material_id": "", "music_id": "", "name": "今年秋天的颜色，是沉...", "path": "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/textReading/1b89339e-cf2c-4d17-8945-7d7c94fc4b1e_000.wav", "query": "", "request_id": "", "resource_id": "7434068983424225843", "search_id": "", "source_platform": 0, "team_id": "", "text_id": "13883903-F48E-4966-AA1E-AF2108FBF99C", "tone_category_id": "", "tone_category_name": "", "tone_effect_id": "", "tone_effect_name": "", "tone_platform": "", "tone_second_category_id": "", "tone_second_category_name": "", "tone_speaker": "zh_female_linjuayi_emo_v2_mars_bigtts", "tone_type": "", "type": "text_to_audio", "video_id": "", "wave_points": []}, "audio_seg": {"cartoon": false, "clip": null, "common_keyframes": [], "enable_adjust": false, "enable_color_curves": true, "enable_color_match_adjust": false, "enable_color_wheels": true, "enable_lut": false, "enable_smart_color_adjust": false, "extra_material_refs": ["5F33502B-D3FE-4D4F-B2A0-DFFB873CF76C", "C0FAD219-DB9B-4DC0-89EB-18D2D10D1BAE", "9B095DBD-F940-423B-9265-335BD86D4536", "D03C22F5-1FFA-43B8-9F70-E78E05C893BF"], "group_id": "", "hdr_settings": null, "id": "C123D045-0810-420B-85BC-53F14AC7F0FF", "intensifies_audio": false, "is_placeholder": false, "is_tone_modify": false, "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": "AB9F09F9-221F-47A3-B3D5-76A994EDA753", "render_index": 0, "responsive_layout": {"enable": false, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0}, "reverse": false, "source_timerange": {"duration": 3100000, "start": 0}, "speed": 1.0, "target_timerange": {"duration": 3100000, "start": 0}, "template_id": "", "template_scene": "default", "track_attribute": 0, "track_render_index": 0, "uniform_scale": null, "visible": true, "volume": 1.0}, "audio_track": {"attribute": 0, "flag": 0, "id": "82E03B17-3878-4A98-9BF6-695D7EB52249", "is_default_name": true, "name": "", "type": "audio"}}')

# 邻居阿姨（5.6.0 实测）：resource_id / tone_speaker 供 5.6 手动「朗读」时选用
VOICE = {
    "jianying:邻居阿姨": {
        "resource_id": "7434068983424225843",
        "tone_speaker": "zh_female_linjuayi_emo_v2_mars_bigtts",
    }
}

# 字幕样式（2026-10-05 用户定：8号字＋黑框＋下1/3）
SUBTITLE_SIZE = 8.0
SUBTITLE_CHECK_FLAG = 7 | 16  # 基础 + 背景
SUBTITLE_Y = -0.33  # 画面下1/3处（单位：半个画布高，负值向下）

UUID_RE = re.compile(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}')

def remap_uuids(obj):
    mapping = {}
    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        if isinstance(o, str) and UUID_RE.fullmatch(o):
            if o not in mapping:
                mapping[o] = str(uuid.uuid4()).upper()
            return mapping[o]
        return o
    return walk(obj), mapping

def probe(path):
    """返回 (时长秒, 宽, 高)；纯音频返回 (时长秒, None, None)。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=width,height", "-of", "json", path],
            capture_output=True, text=True, timeout=20)
        info = json.loads(r.stdout)
        dur = float(info["format"]["duration"])
        for s in info.get("streams", []):
            if s.get("width"):
                return dur, s["width"], s["height"]
        return dur, None, None  # 纯音频：只有时长
    except Exception as e:
        print(f"  ⚠️ ffprobe 失败 {path}: {e}")
    return None

def find_draft_root():
    home = os.path.expanduser("~")
    p = os.path.join(home, "Movies", "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
    return p if os.path.isdir(p) else None

def slowmo_factor(seg):
    s = seg.get("slowmo", False)
    if s is True:
        return 0.5
    if isinstance(s, (int, float)) and 0 < s < 1:
        return float(s)
    return 1.0

def build_text_content(narr, font_path):
    # fill 用官方库同款完整形态（含 render_type）：5.6 在背景开启时对精简形态解析不可靠
    n = len(narr)
    return json.dumps({
        "styles": [{
            "fill": {"alpha": 1.0,
                     "content": {"render_type": "solid",
                                 "solid": {"alpha": 1.0, "color": [1, 1, 1]}}},
            "range": [0, n], "size": SUBTITLE_SIZE,
            "bold": False, "italic": False, "underline": False, "strokes": [],
            "font": {"path": font_path, "id": ""}}],
        "text": narr,
    }, ensure_ascii=False)

def main():
    if sys.platform != "darwin":
        print("只支持 macOS"); sys.exit(1)
    if len(sys.argv) < 2:
        print("用法: python3 edl_to_draft.py edl.json [--media-dir 文件夹]"); sys.exit(1)
    edl = json.load(open(sys.argv[1], encoding="utf-8"))
    media_dir = ""
    if "--media-dir" in sys.argv:
        media_dir = sys.argv[sys.argv.index("--media-dir") + 1]
    segs = edl["segments"]
    if not segs:
        print("❌ EDL 里没有 segments"); sys.exit(1)

    root = find_draft_root()
    if not root:
        print("❌ 没找到草稿目录"); sys.exit(1)
    template = os.path.join(root, "TEMPLATE")
    if not os.path.isdir(template):
        print("❌ 没找到 TEMPLATE"); sys.exit(1)

    draft_name = edl.get("draft_name", "EDL_草稿")
    target = os.path.join(root, draft_name)
    if os.path.isdir(target):
        print(f"删除旧草稿 {draft_name}…"); shutil.rmtree(target)
    print(f"复制 TEMPLATE -> {draft_name} …")
    shutil.copytree(template, target)

    S, _ = remap_uuids(copy.deepcopy(REF_STRUCTS))
    font_path = json.loads(S["text_mat"]["content"])["styles"][0]["font"]["path"]

    W = edl.get("width", 1080); H = edl.get("height", 1920)
    voice_key = edl.get("tts_voice", "jianying:邻居阿姨")
    voice = VOICE.get(voice_key)
    if not voice:
        print(f"❌ 未知音色 {voice_key}，目前支持: {list(VOICE)}"); sys.exit(1)

    videos, texts, speeds = [], [], []
    v_segments, t_segments = [], []
    vo_wavs = []  # (wav路径, 时长us, 文案) → 配音轨
    seg_extra_info = []
    cursor = 0  # 微秒

    for i, seg in enumerate(segs):
        narr = seg["narr"]
        clip = seg["clip"]
        if not os.path.isabs(clip) and media_dir:
            clip = os.path.join(media_dir, clip)
        if not os.path.isfile(clip):
            print(f"❌ 素材不存在: {clip}"); sys.exit(1)
        pr = probe(clip)
        if not pr:
            print(f"❌ 无法读取素材: {clip}"); sys.exit(1)
        clip_dur, vw, vh = pr
        in_s = float(seg.get("in", 0)); out_s = float(seg.get("out", clip_dur))

        # 配音驱动：EDL 的 in/out = 时间线目标时长（按配音时长预估）。
        # 若 EDL 给了真音频（seg["audio"]），直接用真实时长，三轨严格对齐。
        # 素材不够长 → 慢放拉伸填满；够长 → 正常取。
        audio_path = seg.get("audio", "")
        if audio_path:
            if not os.path.isfile(audio_path):
                print(f"❌ 配音不存在: {audio_path}"); sys.exit(1)
            apr = probe(audio_path)
            if not apr:
                print(f"❌ 无法读取配音: {audio_path}"); sys.exit(1)
            want_us = int(apr[0] * 1_000_000)
            vo_wavs.append((audio_path, want_us, narr, cursor))
            print(f"  第{i+1}段：真音频 {apr[0]:.1f}s 驱动")
        else:
            want_us = int((out_s - in_s) * 1_000_000)
        avail_us = int(max(0.5, clip_dur - in_s) * 1_000_000)
        # 慢放：picker 已在 batch 侧决定（含配对同倍率），edl 只执行；
        # 素材仍不够 → 自动慢放拉伸填满（兜底，picker 侧已有 0.5x 下限）。
        base = slowmo_factor(seg)
        need_src_us = int(want_us * base)
        if need_src_us > avail_us:
            factor = avail_us / want_us
            src_us = avail_us
            if factor < 0.5:
                print(f"  ⚠️ 第{i+1}段：素材仅 {avail_us/1e6:.1f}s，"
                      f"{factor:.2f}x 已低于慢放下限 0.5（picker 侧应已避开）")
            else:
                print(f"  第{i+1}段：素材仅 {avail_us/1e6:.1f}s，{factor:.2f}x 慢放拉伸填满")
        else:
            factor = base
            src_us = need_src_us
        tgt_us = want_us  # 字幕=配音=画面，三轨严格对齐

        # --- 视频 ---
        vm = copy.deepcopy(S["video_mat"]); vm["id"] = str(uuid.uuid4()).upper()
        vm["path"] = clip; vm["material_name"] = os.path.basename(clip)
        vm["duration"] = int(clip_dur * 1_000_000)
        vm["width"], vm["height"] = vw, vh
        vm["local_material_id"] = str(uuid.uuid4())
        sp = copy.deepcopy(S["speed"]); sp["id"] = str(uuid.uuid4()).upper()
        sp["speed"] = factor
        cv = copy.deepcopy(S["canvas"]); cv["id"] = str(uuid.uuid4()).upper()
        vseg = copy.deepcopy(S["video_track"]["segments"][0])
        vseg["id"] = str(uuid.uuid4()).upper()
        vseg["material_id"] = vm["id"]
        vseg["speed"] = factor
        vseg["source_timerange"] = {"start": int(in_s * 1_000_000), "duration": src_us}
        vseg["target_timerange"] = {"start": cursor, "duration": tgt_us}
        vseg["extra_material_refs"] = [sp["id"], cv["id"]]
        videos.append(vm); speeds.append(sp); v_segments.append(vseg)
        seg_extra_info.append({"segment_id": vseg["id"], "type": "video"})

        # --- 字幕（段内轮播短字幕）：同一画面/配音段内按自然停顿轮换，
        # 时长按字数比例分配（不伪造词级时间）；画面配音不因字幕切碎 ---
        captions = seg.get("captions") or [narr]
        total_c = sum(len(c) for c in captions) or 1
        cap_cursor = cursor
        for ci, cap in enumerate(captions):
            cap_us = int(want_us * len(cap) / total_c)
            if ci == len(captions) - 1:
                cap_us = cursor + want_us - cap_cursor  # 末条收尾，严格对齐
            tm = copy.deepcopy(S["text_mat"]); tm["id"] = str(uuid.uuid4()).upper()
            tm["content"] = build_text_content(cap, font_path)
            tm["name"] = cap
            tm["text_size"] = SUBTITLE_SIZE
            tm["background_style"] = 1  # 黑框
            tm["background_color"] = "#000000"
            tm["background_alpha"] = 1.0
            tm["background_round_radius"] = 0.0
            tm["check_flag"] = SUBTITLE_CHECK_FLAG
            tm["text_to_audio_ids"] = []
            tseg = copy.deepcopy(S["text_track"]["segments"][0])
            tseg["id"] = str(uuid.uuid4()).upper()
            tseg["material_id"] = tm["id"]
            tseg["source_timerange"] = None
            tseg["target_timerange"] = {"start": cap_cursor, "duration": cap_us}
            tseg["extra_material_refs"] = []
            tseg["clip"]["transform"]["y"] = SUBTITLE_Y  # 下1/3处
            texts.append(tm); t_segments.append(tseg)
            seg_extra_info.append({"segment_id": tseg["id"], "type": "text"})
            cap_cursor += cap_us

        print(f"  第{i+1}段: {narr.replace(chr(10),'/')[:14]}… | {os.path.basename(clip)} {in_s}-{out_s}s"
              f"{f' {factor}x慢放' if factor != 1.0 else ''} | 起 {cursor/1e6:.1f}s")
        cursor += tgt_us

    # --- 配音轨（真音频：每段一个 wav，三轨严格对齐）---
    vo_audios, vo_segments = [], []
    for k, (wav_path, wav_us, narr, start_us) in enumerate(vo_wavs):
        am = copy.deepcopy(S["audio_mat"]); am["id"] = str(uuid.uuid4()).upper()
        am["type"] = "extract_music"  # 官方库本地音频同款 type
        am["path"] = wav_path
        am["name"] = f"配音{k+1}_{narr.replace(chr(10), '')[:10]}"
        am["duration"] = wav_us
        am["local_material_id"] = str(uuid.uuid4())
        am["resource_id"] = ""; am["tone_speaker"] = ""; am["text_id"] = ""
        aseg = copy.deepcopy(S["audio_seg"])
        aseg["id"] = str(uuid.uuid4()).upper()
        aseg["material_id"] = am["id"]
        aseg["volume"] = 1.0
        aseg["source_timerange"] = {"start": 0, "duration": wav_us}
        aseg["target_timerange"] = {"start": start_us, "duration": wav_us}
        aseg["extra_material_refs"] = []
        vo_audios.append(am); vo_segments.append(aseg)
        seg_extra_info.append({"segment_id": aseg["id"], "type": "audio"})
    if vo_segments:
        print(f"  配音轨：{len(vo_segments)} 段真音频已铺")

    # --- BGM（实验性）---
    bgm_audios, bgm_segments = [], []
    bgm_path = edl.get("bgm")
    if bgm_path and os.path.isfile(bgm_path):
        pr = probe(bgm_path)
        if pr:
            bdur = int(pr[0] * 1_000_000)
            bm = copy.deepcopy(S["audio_mat"]); bm["id"] = str(uuid.uuid4()).upper()
            bm["type"] = "music"; bm["path"] = bgm_path
            bm["name"] = os.path.basename(bgm_path)
            bm["duration"] = min(bdur, cursor)
            bm["resource_id"] = ""; bm["tone_speaker"] = ""; bm["text_id"] = ""
            bseg = copy.deepcopy(S["audio_seg"])
            bseg["id"] = str(uuid.uuid4()).upper()
            bseg["material_id"] = bm["id"]
            bseg["volume"] = float(edl.get("bgm_volume", 0.15))
            bseg["source_timerange"] = {"start": 0, "duration": min(bdur, cursor)}
            bseg["target_timerange"] = {"start": 0, "duration": min(bdur, cursor)}
            bseg["extra_material_refs"] = []
            bgm_audios.append(bm); bgm_segments.append(bseg)
            seg_extra_info.append({"segment_id": bseg["id"], "type": "audio"})
            print(f"  BGM: {os.path.basename(bgm_path)}")
    elif bgm_path:
        print(f"  ⚠️ BGM 不存在，跳过: {bgm_path}")

    # --- 组装 draft_info.json ---
    info_path = os.path.join(target, "draft_info.json")
    info = json.load(open(info_path, encoding="utf-8"))
    new_draft_id = str(uuid.uuid4()).upper()

    vt = copy.deepcopy(S["video_track"]); vt["id"] = str(uuid.uuid4()).upper(); vt["segments"] = v_segments
    tt = copy.deepcopy(S["text_track"]); tt["id"] = str(uuid.uuid4()).upper(); tt["segments"] = t_segments
    vot = copy.deepcopy(S["audio_track"]); vot["id"] = str(uuid.uuid4()).upper(); vot["segments"] = vo_segments
    bt = copy.deepcopy(S["audio_track"]); bt["id"] = str(uuid.uuid4()).upper(); bt["segments"] = bgm_segments

    info["materials"]["videos"] = videos
    info["materials"]["texts"] = texts
    info["materials"]["speeds"] = speeds
    info["materials"]["canvases"] = [copy.deepcopy(S["canvas"]) for _ in v_segments]
    for c, vseg in zip(info["materials"]["canvases"], v_segments):
        c["id"] = vseg["extra_material_refs"][1]
    info["materials"]["audios"] = vo_audios + bgm_audios
    info["tracks"] = [vt, tt] + ([vot] if vo_segments else []) + ([bt] if bgm_segments else [])
    info["canvas_config"]["width"] = W
    info["canvas_config"]["height"] = H
    info["canvas_config"]["ratio"] = "original"
    info["fps"] = float(edl.get("fps", 30))
    info["duration"] = cursor
    info["id"] = new_draft_id
    info["update_time"] = int(time.time() * 1_000_000)
    json.dump(info, open(info_path, "w", encoding="utf-8"), ensure_ascii=False)
    info_size = os.path.getsize(info_path)

    # --- 同步 meta ---
    meta_path = os.path.join(target, "draft_meta_info.json")
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path, encoding="utf-8"))
        meta["draft_id"] = new_draft_id
        meta["draft_name"] = draft_name
        meta["draft_fold_path"] = target
        meta["tm_draft_modified"] = info["update_time"]
        meta["tm_duration"] = cursor
        meta["draft_timeline_materials_size_"] = info_size
        meta["draft_segment_extra_info"] = seg_extra_info
        vids = [s["clip"] for s in segs]
        vo_paths = [w for w, _, _, _ in vo_wavs]
        auds = vo_paths + ([bgm_path] if bgm_path and os.path.isfile(bgm_path) else [])
        meta["draft_materials"] = [
            {"type": 0, "value": vids}, {"type": 1, "value": auds},
            {"type": 2, "value": []}, {"type": 3, "value": []},
            {"type": 6, "value": []}, {"type": 7, "value": []},
            {"type": 8, "value": []},
        ]
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False)

    shutil.copy2(info_path, os.path.join(target, "draft_info.json.bak"))
    locked = os.path.join(target, ".locked")
    if os.path.exists(locked):
        os.remove(locked)

    print()
    print("=" * 44)
    print(f"✅ 草稿已生成: {draft_name}（{len(segs)}段，总 {cursor/1e6:.1f}s）")
    print("=" * 44)
    print("去 5.6 里：")
    if vo_segments:
        print("  配音已按真音频铺好，字幕=配音=画面三轨已对齐，无需朗读/回填")
        print("  1. 试听配音，个别不顺的手动微调")
        print("  2. 滤镜、美颜按需调后导出")
    else:
        print("  1. 全选字幕 → 朗读（选邻居阿姨）生成配音")
        print("  2. 核对字幕/配音/画面三轨是否对齐，个别差一点的手动微调")
        print("  3. 滤镜、美颜按需调后导出")

if __name__ == "__main__":
    main()
