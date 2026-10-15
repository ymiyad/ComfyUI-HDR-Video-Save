# ComfyUI-HDR-Video-Save

[English](#english) | [日本語](#日本語)

---

## English

A ComfyUI custom node that saves an HDR-encoded `IMAGE` batch as a **10-bit HEVC HDR MP4 (HLG or PQ / HDR10)** with correct color tagging.

It is designed as the missing output stage for **NVIDIA RTX TrueHDR** ([ComfyUI_Nvidia_VFX_Nodes](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes)). TrueHDR returns BT.2020 HLG/PQ signal values as a regular `IMAGE`. A ComfyUI `IMAGE` carries no color-space metadata, so standard video save nodes encode it as 8-bit SDR and the result no longer plays back as HDR. This node fixes that.

### Features

- Frames are piped straight to ffmpeg as **16-bit RGB**. There are no intermediate image files and no 8-bit quantization.
- RGB → YUV conversion uses the **BT.2020 matrix**. Using the default BT.601 matrix is a common mistake that causes a color shift.
- Output tags: BT.2020 primaries, BT.2020nc matrix, limited range, plus the **HLG (arib-std-b67)** or **PQ (smpte2084)** transfer function.
- **HDR10 static metadata** (mastering display, MaxCLL / MaxFALL) is embedded for PQ output when encoding with libx265.
- Encoders: `libx265` or `hevc_nvenc` (GPU).
- Optional `AUDIO` input, muxed into the MP4 as AAC.
- `hvc1` tag for QuickTime / Apple playback, and `faststart` for streaming.
- Handles odd resolutions by padding to even dimensions, and accepts RGBA or grayscale input.

### Installation

```
cd ComfyUI/custom_nodes
git clone https://github.com/ymiyad/ComfyUI-HDR-Video-Save.git
```

Restart ComfyUI. No extra Python packages are required.

**ffmpeg** must be available. The node looks for it in this order:

1. The `FFMPEG_PATH` environment variable
2. `ffmpeg` on `PATH`
3. The binary bundled with `imageio-ffmpeg`, if that package is installed

The ffmpeg build must include `libx265`; to use the `hevc_nvenc` encoder, it must also include `hevc_nvenc`.

### Usage

The node appears under the **video** category as **Save HDR Video (HLG / PQ)**.

```
Load Video → (RTX Video Super Resolution / Frame Generation) → RTX TrueHDR → Save HDR Video
```

Set `transfer` to match the TrueHDR `output_colorspace` setting:

| TrueHDR `output_colorspace` | This node `transfer` |
| --- | --- |
| `HDR` (BT.2020 / HLG) | `HLG` |
| `HDR PQ` (BT.2020 / PQ) | `PQ (HDR10)` |

Run super resolution and frame generation **before** TrueHDR. Those effects expect SDR input.

### Inputs

| Input | Default | Description |
| --- | --- | --- |
| `images` | — | HDR-encoded `IMAGE` batch (BT.2020, HLG or PQ, normalized 0–1). |
| `filename_prefix` | `HDR/video` | Output path inside the ComfyUI output folder. |
| `fps` | `24.0` | Frame rate. After frame generation, multiply the source fps by the multiplier. |
| `transfer` | `HLG` | `HLG` or `PQ (HDR10)`. |
| `encoder` | `libx265` | `libx265` or `hevc_nvenc`. |
| `quality` | `16` | CRF for libx265, CQ for NVENC. Lower values mean higher quality. |
| `x265_preset` | `slow` | x265 speed preset (libx265 only). |
| `peak_luminance` | `650` | PQ only. Mastering peak luminance and MaxCLL in nits. Set it to the same value as TrueHDR `luminance`. |
| `max_fall` | `400` | PQ only. MaxFALL in nits. |
| `audio` | (optional) | Audio to mux into the file as AAC 320 kbps. Trimmed to the video length. |

Output: `filepath` (STRING), the path of the saved MP4.

### Notes

- **HLG** needs no metadata and still looks reasonable on SDR displays. Use it unless you specifically need HDR10.
- **PQ + hevc_nvenc**: the color tags are written, but the HDR10 static metadata is **not** embedded. Use libx265 for strict HDR10 delivery.
- The input values must already be HDR-encoded, for example the output of TrueHDR. Feeding ordinary SDR images produces incorrect results.
- Frames are streamed to ffmpeg one at a time, so encoding adds little memory. The `IMAGE` batch itself is still held in memory, so split long videos into chunks.

### Verified

- Output is HEVC Main 10, `yuv420p10le`, with `hvc1` tagging and correct BT.2020 HLG/PQ tags, checked with ffprobe.
- PQ output contains the Mastering Display and Content Light Level SEI.
- Plays back as HDR on macOS.

### License

MIT (see `LICENSE`)

---

## 日本語

HDR符号化済みの `IMAGE` バッチを、正しい色タグ付きの **10bit HEVC HDR MP4（HLG または PQ / HDR10）** として保存するComfyUIカスタムノードです。

**NVIDIA RTX TrueHDR**（[ComfyUI_Nvidia_VFX_Nodes](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes)）の出力を保存するために作りました。TrueHDRはBT.2020のHLG/PQ信号値を通常の `IMAGE` として返します。ところがComfyUIの `IMAGE` は色空間の情報を持たないため、一般的な動画保存ノードでは8bit SDRとしてエンコードされ、HDRとして再生されなくなります。このノードはその問題を解決します。

### 特長

- **16bit RGB** のままffmpegへ直接パイプします。中間の連番画像は作らず、8bitへの量子化も起きません。
- RGB→YUVの変換には **BT.2020の行列** を使います。ffmpegの既定（BT.601）のまま変換すると色ずれが起きますが、その対策済みです。
- 出力には次のタグを付けます。BT.2020の色域、BT.2020ncの行列、リミテッドレンジ、そして **HLG（arib-std-b67）** または **PQ（smpte2084）** の伝達関数です。
- PQをlibx265でエンコードすると、**HDR10静的メタデータ**（Mastering Display、MaxCLL/MaxFALL）を埋め込みます。
- エンコーダは `libx265` と `hevc_nvenc`（GPU）から選べます。
- `AUDIO` 入力は任意です。つなぐとAACでMP4に多重化します。
- QuickTimeやApple機器で再生できるよう `hvc1` タグを付け、ストリーミング向けに `faststart` も有効にしています。
- 奇数解像度は偶数に合わせてパディングします。RGBAやグレースケールの入力にも対応しています。

### インストール

```
cd ComfyUI/custom_nodes
git clone https://github.com/ymiyad/ComfyUI-HDR-Video-Save.git
```

ComfyUIを再起動してください。追加のPythonパッケージは不要です。

**ffmpeg** が必要です。次の順に探します。

1. 環境変数 `FFMPEG_PATH`
2. `PATH` 上の `ffmpeg`
3. `imageio-ffmpeg` パッケージ同梱のバイナリ（インストールされている場合）

ffmpegは `libx265` を含むビルドが必要です。`hevc_nvenc` エンコーダを使う場合は、`hevc_nvenc` も含まれている必要があります。

### 使い方

**video** カテゴリに **Save HDR Video (HLG / PQ)** として表示されます。

```
Load Video → (RTX Video Super Resolution / Frame Generation) → RTX TrueHDR → Save HDR Video
```

`transfer` はTrueHDRの `output_colorspace` に合わせて設定します。

| TrueHDR `output_colorspace` | このノードの `transfer` |
| --- | --- |
| `HDR`（BT.2020 / HLG） | `HLG` |
| `HDR PQ`（BT.2020 / PQ） | `PQ (HDR10)` |

超解像やフレーム補間はSDR入力を前提としているので、TrueHDRより**前**にかけてください。

### 入力

| 入力 | 既定値 | 説明 |
| --- | --- | --- |
| `images` | — | HDR符号化済みの `IMAGE` バッチ（BT.2020、HLGまたはPQ、0〜1に正規化）。 |
| `filename_prefix` | `HDR/video` | ComfyUIのoutputフォルダ内の保存先。 |
| `fps` | `24.0` | フレームレート。フレーム補間後は、元のfpsに倍率を掛けた値にします。 |
| `transfer` | `HLG` | `HLG` または `PQ (HDR10)`。 |
| `encoder` | `libx265` | `libx265` または `hevc_nvenc`。 |
| `quality` | `16` | libx265ではCRF、NVENCではCQ。値が小さいほど高画質です。 |
| `x265_preset` | `slow` | x265の速度プリセット（libx265のみ）。 |
| `peak_luminance` | `650` | PQ用。マスタリングのピーク輝度とMaxCLL（nit）。TrueHDRの `luminance` と同じ値にします。 |
| `max_fall` | `400` | PQ用。MaxFALL（nit）。 |
| `audio` | （任意） | AAC 320kbpsで多重化する音声。動画の長さで切り詰めます。 |

出力は `filepath`（STRING）で、保存したMP4のパスです。

### 注意点

- **HLG** はメタデータが不要で、SDRのディスプレイでもそれなりに見えます。HDR10での納品が必要でなければHLGをおすすめします。
- **PQとhevc_nvenc** の組み合わせでは、色タグは付きますがHDR10の静的メタデータは**入りません**。厳密なHDR10が必要な場合はlibx265を使ってください。
- 入力はTrueHDRの出力のような、HDR符号化済みの値である必要があります。通常のSDR画像を入れると正しい結果になりません。
- フレームは1枚ずつffmpegに送るので、エンコードによるメモリの増加はわずかです。ただし `IMAGE` バッチ自体はメモリ上にあるため、長い動画は分割して処理してください。

### 動作確認

- ffprobeで、出力がHEVC Main 10、`yuv420p10le`、`hvc1` タグで、BT.2020 HLG/PQのタグが正しいことを確認しました。
- PQ出力にMastering DisplayとContent Light LevelのSEIが入っていることを確認しました。
- macOS上でHDRとして再生されることを確認しました。

### ライセンス

MIT（`LICENSE` を参照）
