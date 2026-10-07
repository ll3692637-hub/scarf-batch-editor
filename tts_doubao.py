#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包 Seed-TTS v3 单向流式 HTTP → 直出 16-bit PCM wav（24kHz 单声道）
只用 Python 标准库，Mac 零依赖。

用法：
    python3 tts_doubao.py --key KEY --text "你好，世界" --out out.wav
    [--speaker ICL_uranus_zh_female_zhixingwenwan_tob]
    [--resource seed-tts-2.0] [--rate 0]

    --rate 语速：-50~100，0=正常（(倍速-1)*100）
    key 也可走环境变量 DOUBAO_TTS_KEY（推荐，避免 key 落在 shell 历史里）
"""
import argparse, base64, json, os, struct, sys, uuid
import urllib.request, urllib.error

API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DEFAULT_SPEAKER = "zh_female_cancan_uranus_bigtts"  # 知性灿灿 2.0（用户 2026-10-05 晚改：试试年纪大一点的）
DEFAULT_RESOURCE = "seed-tts-2.0"    # uranus 系 2.0 音色
FALLBACK_RESOURCE = "seed-icl-2.0"   # ICL/S_ 系复刻音色；40000001 时自动换这个重试一次
SAMPLE_RATE = 24000


class TtsError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"[doubao-tts {code}] {message}")


def _hint(code, message):
    m = (message or "").lower()
    if code in (401, 403, 40300001):
        return "→ 检查 Key 是否为「豆包语音控制台」签发的 API Key（火山方舟的推理 Key 不通用），并确认已开通语音合成服务"
    if code == 40000001:
        return "→ 音色 ID 与 resource_id 不匹配（或音色 ID 写错）"
    if code == 40402003:
        return "→ 文本超长，请分段合成"
    if "quota" in m or "balance" in m or "grant" in m:
        return "→ 免费额度/余额不足，去控制台查看"
    return ""


def _request_once(text, api_key, speaker, resource_id, speech_rate, timeout):
    body = json.dumps({
        "user": {"uid": "batch_tts"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {"format": "pcm", "sample_rate": SAMPLE_RATE,
                             "speech_rate": speech_rate},
        },
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Content-Type": "application/json",
                 "X-Api-Key": api_key,
                 "X-Api-Resource-Id": resource_id,
                 "X-Api-Request-Id": str(uuid.uuid4())},
        method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = ""
        raise TtsError(e.code, f"HTTP {e.code} {detail} {_hint(e.code, detail)}")
    except Exception as e:
        raise TtsError("NET", f"网络错误：{e}")

    # 响应是 HTTP chunked 里的拼接 JSON（不一定换行分隔）→ 增量解码
    pcm_parts, final_code, final_msg = [], None, ""
    dec, i, n = json.JSONDecoder(), 0, len(raw)
    while i < n:
        while i < n and raw[i] in " \n\r\t":
            i += 1
        if i >= n:
            break
        try:
            obj, i = dec.raw_decode(raw, i)
        except json.JSONDecodeError:
            break
        if not isinstance(obj, dict):
            continue
        data = obj.get("data")
        if isinstance(data, str) and data:
            pcm_parts.append(base64.b64decode(data))
        if "code" in obj:
            final_code, final_msg = obj["code"], obj.get("message", "")
    if final_code not in (0, 20000000, None):
        raise TtsError(final_code, f"{final_msg} {_hint(final_code, final_msg)}")
    pcm = b"".join(pcm_parts)
    if not pcm:
        raise TtsError("EMPTY", f"服务端未返回音频数据（code={final_code} msg={final_msg}）")
    return pcm


def write_wav(pcm_bytes, out_path, sample_rate=SAMPLE_RATE):
    n = len(pcm_bytes)
    with open(out_path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                                      sample_rate * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", n) + pcm_bytes)
    return n / (sample_rate * 2)  # 时长（秒）


def synth(text, out_wav, api_key, speaker=DEFAULT_SPEAKER,
          resource_id=DEFAULT_RESOURCE, speech_rate=0, timeout=60):
    """合成一段文本 → wav 文件。返回音频时长（秒）。失败抛 TtsError。"""
    text = (text or "").strip()
    if not text:
        raise TtsError("ARG", "文本为空")
    if not api_key:
        raise TtsError("ARG", "缺少 API Key（--key 或环境变量 DOUBAO_TTS_KEY）")
    speech_rate = max(-50, min(100, int(speech_rate)))
    try:
        pcm = _request_once(text, api_key, speaker, resource_id,
                            speech_rate, timeout)
    except TtsError as e:
        # resource 不匹配 → 自动换 seed-icl-2.0 重试一次
        if e.code == 40000001 and resource_id != FALLBACK_RESOURCE:
            print(f"  ⚠️ {resource_id} 报参数错误，换 {FALLBACK_RESOURCE} 重试…")
            pcm = _request_once(text, api_key, speaker, FALLBACK_RESOURCE,
                                speech_rate, timeout)
        else:
            raise
    dur = write_wav(pcm, out_wav)
    return dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("DOUBAO_TTS_KEY", ""))
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--speaker", default=DEFAULT_SPEAKER)
    ap.add_argument("--resource", default=DEFAULT_RESOURCE)
    ap.add_argument("--rate", type=int, default=0)
    a = ap.parse_args()
    try:
        dur = synth(a.text, a.out, a.key, a.speaker, a.resource, a.rate)
    except TtsError as e:
        print(f"❌ {e}"); sys.exit(1)
    print(f"✅ {a.out}（{dur:.1f}s)")


if __name__ == "__main__":
    main()
