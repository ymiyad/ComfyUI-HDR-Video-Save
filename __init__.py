"""
ComfyUI-HDR-Video-Save
----------------------
Encodes an IMAGE batch that already carries an HDR signal (e.g. the output of
NVIDIA "RTX TrueHDR": BT.2020 + HLG or PQ, normalized 0-1) into a 10-bit HEVC
MP4 with proper HDR color tagging. Frames are piped to ffmpeg as 16-bit RGB,
so no intermediate image files and no 8-bit quantization.
"""

import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
import torch

import folder_paths


def _find_ffmpeg():
    exe = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError(
            "ffmpeg が見つかりません。PATH に通すか、環境変数 FFMPEG_PATH を設定するか、"
            "ComfyUI の Python に imageio-ffmpeg を入れてください。"
        )


def _write_wav(audio, path):
    """ComfyUI AUDIO dict -> 16-bit PCM WAV."""
    wf = audio["waveform"]
    sr = int(audio["sample_rate"])
    if wf.dim() == 3:
        wf = wf[0]  # (C, S)
    data = wf.detach().float().cpu().clamp(-1.0, 1.0).numpy().T  # (S, C)
    pcm = (data * 32767.0).round().astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class SaveHDRVideo:
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filepath",)
    FUNCTION = "save"
    CATEGORY = "video"
    DESCRIPTION = (
        "HLG / PQ 符号化済みの BT.2020 IMAGE バッチ（RTX TrueHDR の出力など）を "
        "10bit HEVC の HDR MP4 として保存します。"
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "HDR/video"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "transfer": (["HLG", "PQ (HDR10)"], {"default": "HLG",
                             "tooltip": "TrueHDR の output_colorspace と合わせる（HDR→HLG, HDR PQ→PQ）"}),
                "encoder": (["libx265", "hevc_nvenc"], {"default": "libx265",
                            "tooltip": "PQ の HDR10 メタデータ（mastering display / MaxCLL）は libx265 のみ埋め込み"}),
                "quality": ("INT", {"default": 16, "min": 0, "max": 51,
                            "tooltip": "libx265: CRF / hevc_nvenc: CQ（小さいほど高画質）"}),
                "x265_preset": (["ultrafast", "superfast", "veryfast", "faster", "fast",
                                 "medium", "slow", "slower", "veryslow"], {"default": "slow"}),
                "peak_luminance": ("INT", {"default": 650, "min": 100, "max": 10000,
                                   "tooltip": "PQ 用。TrueHDR の luminance と同じ値に"}),
                "max_fall": ("INT", {"default": 400, "min": 1, "max": 10000,
                             "tooltip": "PQ 用 MaxFALL (nits)"}),
            },
            "optional": {
                "audio": ("AUDIO",),
            },
        }

    def save(self, images, filename_prefix, fps, transfer, encoder, quality,
             x265_preset, peak_luminance, max_fall, audio=None):
        ffmpeg = _find_ffmpeg()
        if images.dim() != 4 or images.shape[0] == 0:
            raise ValueError("images は空でない (B, H, W, C) の IMAGE バッチが必要です")

        n, h, w, c = images.shape
        is_pq = transfer.startswith("PQ")
        trc = "smpte2084" if is_pq else "arib-std-b67"

        out_dir = folder_paths.get_output_directory()
        full_dir, fname, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, out_dir, w, h)
        os.makedirs(full_dir, exist_ok=True)
        out_path = os.path.join(full_dir, f"{fname}_{counter:05}_{'pq' if is_pq else 'hlg'}.mp4")

        pix_fmt = "p010le" if encoder == "hevc_nvenc" else "yuv420p10le"
        vf = ("pad=ceil(iw/2)*2:ceil(ih/2)*2,"
              "scale=out_color_matrix=bt2020:out_range=tv:flags=accurate_rnd+full_chroma_int,"
              f"format={pix_fmt}")

        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{w}x{h}",
               "-r", f"{fps}", "-i", "-"]

        wav_path = None
        if audio is not None:
            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _write_wav(audio, wav_path)
            cmd += ["-i", wav_path]

        cmd += ["-map", "0:v:0"]
        if wav_path:
            cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "320k", "-shortest"]

        cmd += ["-vf", vf]

        if encoder == "libx265":
            x265 = [f"colorprim=bt2020", f"transfer={trc}", "colormatrix=bt2020nc",
                    "range=limited", "repeat-headers=1"]
            if is_pq:
                x265 += ["hdr10=1", "hdr10-opt=1",
                         # P3-D65 mastering primaries, min 0.005 nit
                         f"master-display=G(13250,34500)B(7500,3000)R(34000,16000)"
                         f"WP(15635,16450)L({int(peak_luminance) * 10000},50)",
                         f"max-cll={int(peak_luminance)},{int(max_fall)}"]
            cmd += ["-c:v", "libx265", "-preset", x265_preset, "-crf", str(quality),
                    "-x265-params", ":".join(x265)]
        else:
            if is_pq:
                print("[SaveHDRVideo] 注意: hevc_nvenc では HDR10 静的メタデータは埋め込まれません"
                      "（色タグのみ）。厳密な HDR10 が必要なら libx265 を使ってください。")
            cmd += ["-c:v", "hevc_nvenc", "-profile:v", "main10", "-preset", "p6",
                    "-rc", "vbr", "-cq", str(quality), "-b:v", "0"]

        cmd += ["-color_primaries", "bt2020", "-color_trc", trc,
                "-colorspace", "bt2020nc", "-color_range", "tv",
                "-tag:v", "hvc1", "-movflags", "+faststart", out_path]

        err = tempfile.TemporaryFile()
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        try:
            for i in range(n):
                frame = images[i]
                if c == 4:
                    frame = frame[..., :3]
                elif c == 1:
                    frame = frame.expand(-1, -1, 3)
                arr = (frame.detach().float().cpu().clamp(0.0, 1.0) * 65535.0 + 0.5)
                proc.stdin.write(arr.to(torch.int32).numpy().astype("<u2").tobytes())
            proc.stdin.close()
            rc = proc.wait()
        except BrokenPipeError:
            rc = proc.wait()
        finally:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

        if rc != 0:
            err.seek(0)
            msg = err.read().decode(errors="replace")
            err.close()
            if os.path.exists(out_path):
                os.remove(out_path)  # 壊れた MP4 を残さない
            raise RuntimeError(f"ffmpeg がエラー終了しました (code {rc}):\n{msg}")
        err.close()

        print(f"[SaveHDRVideo] saved: {out_path}")
        return {"ui": {"text": [out_path]}, "result": (out_path,)}


NODE_CLASS_MAPPINGS = {"SaveHDRVideo": SaveHDRVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveHDRVideo": "Save HDR Video (HLG / PQ)"}
