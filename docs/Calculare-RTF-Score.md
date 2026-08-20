はい。`nvidia/parakeet-tdt_ctc-0.6b-ja` のRTFは、**Kotoba-Whisper v2.0が評価に使っている3つの日本語ASRデータセットを共通入力にして、実測時間 ÷ 音声総時間で算出**するのが最も比較として公平です。

Hugging Face上で確認したところ、Kotoba-Whisper v2.0が評価に使っているのは次の3つです。([Hugging Face][1])

| 用途                    | Dataset                                 |
| --------------------- | --------------------------------------- |
| Common Voice日本語       | `japanese-asr/ja_asr.common_voice_8_0`  |
| JSUT                  | `japanese-asr/ja_asr.jsut_basic5000`    |
| ReazonSpeech held-out | `japanese-asr/ja_asr.reazonspeech_test` |

Hugging Face側でもこの3 dataset がそれぞれAudio/TextのParquet datasetとして公開されています。Parakeet側のModel CardもJSUT Basic 5000とCommon Voice 8を評価対象に含めています。([Hugging Face][2])

## 1. RTFの定義

一番基本的には、

[
RTF = \frac{\text{ASR処理時間}}{\text{入力音声の総再生時間}}
]

です。

例えば音声1時間を3分で処理したなら、

[
RTF = \frac{180}{3600}=0.05
]

です。

逆に何倍速かは、

[
\text{Realtime speed}=\frac{1}{RTF}
]

なので、

|   RTF |  処理速度 |
| ----: | ----: |
|   1.0 |   1倍速 |
|   0.5 |   2倍速 |
|   0.1 |  10倍速 |
|  0.05 |  20倍速 |
|  0.02 |  50倍速 |
|  0.01 | 100倍速 |
| 0.005 | 200倍速 |

となります。

今回のクラウドGPU原価計算ではこの **RTFがそのままコスト計算に使えます**。

たとえばL4が `$0.49/GPU-h` なら、

[
\text{1 audio-hour原価}=0.49\times RTF
]

です。

---

# 2. Kotoba-Whisper v2.0のModel Cardに絶対RTFはあるか

ここは重要で、**Kotoba-Whisper v2.0のModel Cardには絶対値としてのRTFは掲載されていません。**

掲載されているのは、

> Whisper large-v3比で **6.3x faster**

という**Relative Latency**です。Kotoba v2.0はDistil-Whisper `distil-large-v3` と同じ構成を採用しているため、その6.3倍という速度改善値を引用しています。([Hugging Face][3])

つまりModel Cardから分かるのは、

| Model               | Relative latency / speed |
| ------------------- | -----------------------: |
| Whisper large-v3    |                      1.0 |
| Kotoba-Whisper v2.0 |          **6.3x faster** |

までです。

たとえば同じGPUでWhisper large-v3のRTFが0.126なら、

[
0.126/6.3=0.020
]

なのでKotobaがRTF ≈ 0.02になる、という**推定**はできます。

しかし、

> Kotoba v2.0 RTF = 0.02

とModel Cardから直接言えるわけではありません。

---

# 3. 実はKotoba公式Repositoryに速度測定コードがある

これは今回かなり便利です。

Kotoba公式Repositoryには、

```text
run_speed_eval.py
```

があります。([GitHub][4])

中では、

```python
start = time()
transcription = pipe(...)
elapsed.append(time() - start)
```

という形で推論時間を15回測り、最初の1回をwarm-upとして捨てています。([GitHub][4])

したがって、

```text
elapsed_seconds / audio_duration_seconds
```

を追加すれば、そのままRTFになります。

ただしこの公式speed scriptは**実データセットではなく生成したdummy audio**を使っています。

今回の目的は、

> ParakeetとKotobaを同じ日本語ASR datasetで比較

なので、私はこれをそのまま使うより**評価dataset版RTF benchmarkを作る**ことを勧めます。

---

# 4. 最も公平なベンチマーク条件

最低でも次を固定してください。

```text
GPU       : 同一
CUDA      : 同一
dtype     : FP16/BF16
audio     : 同一
sampling  : 16 kHz mono
dataset   : 同一
batch     : 同一または両者最適値を別途記録
decoder   : 明記
warmup    : 除外
model load: 除外
```

ParakeetのModel Cardでは入力条件が明確に、

**16,000 Hz / mono / WAV**

です。([Hugging Face][2])

ですので、3 datasetを最初に全部、

```text
16kHz mono PCM WAV
```

へ正規化してしまうのがおすすめです。

これは製品側で予定しているOpus 24 kbpsとは分けます。

```text
Network
Opus 24 kbps
     ↓ decode

Benchmark / Model input
PCM16 16k mono
```

です。

**Opusのdecode時間をRTFへ含めるかどうか**は別途後述します。

---

# 5. RTFは2種類測るべき

商用サービス化を考えているなら、私は必ず2つ測ります。

### Model RTF

```text
model input ready
       ↓
GPU inference
       ↓
transcript

RTF_model
```

これはモデルそのものの性能比較用。

### Service RTF

```text
Opus
 ↓
decode
 ↓
resample
 ↓
batch
 ↓
GPU inference
 ↓
postprocess
 ↓
JSON

RTF_service
```

こちらは**RunPod/HFの本当の原価計算**に使います。

たとえば、

```text
RTF_model   = 0.018
RTF_service = 0.023
```

なら料金計算では0.023を使うべきです。

---

# 6. 一番簡単な測定方法

例えばdataset全部の音声長が、

```text
audio_duration_total = 18,000 sec
```

つまり5時間だったとします。

推論全体が、

```text
elapsed = 270 sec
```

なら、

[
RTF=270/18000=0.015
]

つまり、

[
1/0.015=66.7x
]

です。

**個々の音声のRTFを平均しないこと**も重要です。

悪い計算：

```python
mean([
    inference1 / duration1,
    inference2 / duration2,
    ...
])
```

より、

```python
total_inference_time / total_audio_duration
```

を主指標にします。

短いclipが大量にあるdatasetでは特に差が出ます。

---

# 7. Parakeet用の実測コード

最低限ならこういう形です。

```python
import time
import torch
import nemo.collections.asr as nemo_asr

MODEL = "nvidia/parakeet-tdt_ctc-0.6b-ja"

model = nemo_asr.models.ASRModel.from_pretrained(MODEL)
model = model.cuda()
model.eval()

wav_files = [
    # あらかじめ16kHz mono WAVへ変換した評価ファイル
]

audio_seconds = [
    # 各wavの秒数
]

# warmup
with torch.inference_mode():
    model.transcribe(wav_files[:8])

torch.cuda.synchronize()

start = time.perf_counter()

with torch.inference_mode():
    output = model.transcribe(
        wav_files,
        batch_size=16,
    )

torch.cuda.synchronize()

elapsed = time.perf_counter() - start

total_audio = sum(audio_seconds)

rtf = elapsed / total_audio
rtfx = total_audio / elapsed

print(f"audio     = {total_audio:.2f} sec")
print(f"inference = {elapsed:.2f} sec")
print(f"RTF       = {rtf:.6f}")
print(f"RTFx      = {rtfx:.2f}x")
```

**`torch.cuda.synchronize()` は重要です。**

CUDAは非同期実行なので、これを入れず単純に、

```python
start = perf_counter()
model(...)
elapsed = perf_counter() - start
```

とするとGPU処理終了前に時計を止めてしまい、過度に速い値になる場合があります。

---

# 8. Kotoba v2.0も同じように測る

Kotoba公式はTransformers pipelineを使用しています。Model Cardのモデル自体は756M parametersのWhisper系です。([Hugging Face][3])

例えば、

```python
import time
import torch
from transformers import pipeline

MODEL = "kotoba-tech/kotoba-whisper-v2.0"

pipe = pipeline(
    "automatic-speech-recognition",
    model=MODEL,
    torch_dtype=torch.float16,
    device="cuda:0",
)

inputs = [
    {"path": path}
    for path in wav_files
]

# warmup
pipe(
    inputs[:8],
    batch_size=8,
    generate_kwargs={
        "language": "ja",
        "task": "transcribe",
    },
)

torch.cuda.synchronize()

start = time.perf_counter()

outputs = pipe(
    inputs,
    batch_size=16,
    generate_kwargs={
        "language": "ja",
        "task": "transcribe",
    },
)

torch.cuda.synchronize()

elapsed = time.perf_counter() - start

total_audio = sum(audio_seconds)

print("RTF :", elapsed / total_audio)
print("RTFx:", total_audio / elapsed)
```

ただし、実際にはKotoba側のofficial evaluation setupに寄せるなら、

```text
batch_size = 16
chunk_length_s = 15
attention = sdpa
```

を基準にするのが良いです。公式 `run_short_form_eval.py` のdefaultもこの設定です。([GitHub][5])

---

# 9. Datasetは3つ全部測った方がよい

今回なら私は、

```text
japanese-asr/ja_asr.common_voice_8_0
japanese-asr/ja_asr.jsut_basic5000
japanese-asr/ja_asr.reazonspeech_test
```

を個別測定し、

最後にcombinedも出します。

例えば、

| Dataset         | Audio h | Parakeet RTF | Kotoba RTF | Parakeet CER | Kotoba CER |
| --------------- | ------: | -----------: | ---------: | -----------: | ---------: |
| Common Voice 8  |       x |            … |          … |          7.1 |        9.2 |
| JSUT Basic 5000 |       x |            … |          … |          6.4 |        8.4 |
| ReazonSpeech    |       x |            … |          … |            — |       11.6 |
| **Combined**    |       x |        **…** |      **…** |            — |          — |

CERについては既報値があります。

Parakeet Model CardではTDT decoderで、

* JSUT: **6.4%**
* Common Voice 8: **7.1%**

です。([Hugging Face][2])

Kotoba v2.0では、

* Common Voice 8: **9.2%**
* JSUT: **8.4%**
* ReazonSpeech held-out: **11.6%**

です。([Hugging Face][3])

なので少なくともこの2 datasetでは、**Parakeetの既報CERの方がKotoba v2.0より低い**です。

---

# 10. ParakeetはTDTとCTCを両方測る価値がある

このモデルは名前通り、

```text
TDT
+
CTC
```

のHybridです。

NVIDIAによるとdefaultはTDTで、

```python
model.transcribe(...)
```

するとTDT decoderを使用します。CTCへ切り替えることもできます。([Hugging Face][2])

精度はModel Card上、

| Decoder | JSUT CER | CV8 CER |
| ------- | -------: | ------: |
| **TDT** |  **6.4** | **7.1** |
| CTC     |      6.5 |     7.2 |

と非常に近いです。([Hugging Face][2])

しかし速度特性は違う可能性があります。

NVIDIAはTDTについて、duration predictionによりblank予測を飛ばせるため**推論速度を大幅に改善できる構造**だと説明しています。([Hugging Face][2])

したがって、

```text
Parakeet TDT
Parakeet CTC
Kotoba
```

の3列を測ると面白いです。

---

# 11. Batch sizeを1つだけ測らない

クラウドSaaSを考えているなら、ここが非常に重要です。

```text
batch = 1
4
8
16
32
64
```

を測ります。

例えば結果が仮に、

| batch |   RTF | RTFx |
| ----: | ----: | ---: |
|     1 | 0.025 |  40x |
|     4 | 0.012 |  83x |
|     8 | 0.008 | 125x |
|    16 | 0.005 | 200x |
|    32 | 0.004 | 250x |

となれば、1000ユーザーからリクエストをqueueしてbatchingすることでGPU原価が激減します。

特に今回のサービスは、

```text
1000 users
     ↓
API Queue
     ↓
Dynamic batching
     ↓
GPU
```

なので、**batch=1 RTFよりthroughput RTFの方が事業上重要**です。

---

# 12. latency RTFとthroughput RTFを分ける

したがって最終結果には、

```text
RTF latency
batch=1

RTF throughput
batch=16/32
```

の両方を載せることを勧めます。

例えば、

```text
Parakeet / L4

batch 1:
RTF 0.020
50x realtime

batch 32:
RTF 0.004
250x realtime
```

のようにします。

ユーザー待ち時間を考えるならbatch=1。

サーバー原価を考えるならbatch throughput。

---

# 13. Kotoba公式の「6.3x」は今回のRTF比較とは別物

これは混同しない方がよいです。

Kotoba Model Cardの、

```text
6.3x faster
```

は、

**large-v3に対するRelative Latency**

です。([Hugging Face][3])

一方こちらで測る、

```text
RTF = 0.018
```

は絶対的な実行速度です。

したがって最終benchmark tableは、

| Model    | GPU | Batch |   RTF | RTFx | CER |
| -------- | --- | ----: | ----: | ---: | --: |
| Parakeet | L4  |     1 | 0.0xx |  xx× |   … |
| Parakeet | L4  |    16 | 0.0xx |  xx× |   … |
| Kotoba   | L4  |     1 | 0.0xx |  xx× |   … |
| Kotoba   | L4  |    16 | 0.0xx |  xx× |   … |

にするのが適切です。

---

## 今回の用途なら私はこう測ります

最終的にクラウド原価へ使いたいので、まず **L4** で、

```text
Models
────────────────────────
nvidia/parakeet-tdt_ctc-0.6b-ja
kotoba-tech/kotoba-whisper-v2.0


Datasets
────────────────────────
CommonVoice 8 Japanese
JSUT Basic 5000
ReazonSpeech held-out


Conditions
────────────────────────
16 kHz
mono
same WAV inputs
FP16/BF16
batch = 1, 8, 16, 32
3 warmups
3 benchmark passes


Metrics
────────────────────────
RTF_model
RTFx
audio-hours/GPU-hour
CER
VRAM peak
GPU utilization
```

を記録します。

さらに製品環境用として、

```text
Opus 24 kbps upload
 ↓
decode
 ↓
ASR
 ↓
JSON
```

全体の、

**`RTF_service`**

も別測定します。

これで以前の料金計算が、

[
GPU原価/ユーザー
==========

月間audio-hours
\times RTF_{service}
\times GPU単価
]

としてかなり正確に出せます。

特に `nvidia/parakeet-tdt_ctc-0.6b-ja` はModel Cardに**絶対RTFが掲載されていない**ので、今回の用途では「既報値を探す」より、この3つのKotoba評価datasetを使って**L4/3090/T4それぞれで実測する方が価値があります**。Kotoba側についても絶対RTFはModel Cardからは確認できず、確認できる速度指標はlarge-v3比6.3倍です。([Hugging Face][3])

必要であれば次に、この条件をそのまま **HF JobsでL4/T4/A10Gなどに投げてParakeetとKotobaのRTF・CER・VRAMをCSV/JSONへ出すベンチマークスクリプト**にできます。これならRunPod側でも同じDocker imageを実行して、$/audio-hourまで直接比較できます。

[1]: https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0/blob/main/README.md?utm_source=chatgpt.com "README.md · kotoba-tech/kotoba-whisper-v2.0 at main"
[2]: https://huggingface.co/nvidia/parakeet-tdt_ctc-0.6b-ja "nvidia/parakeet-tdt_ctc-0.6b-ja · Hugging Face"
[3]: https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0?utm_source=chatgpt.com "kotoba-tech/kotoba-whisper-v2.0 · Hugging Face"
[4]: https://github.com/kotoba-tech/kotoba-whisper/blob/main/run_speed_eval.py?utm_source=chatgpt.com "kotoba-whisper/run_speed_eval.py at main · kotoba-tech/kotoba-whisper · GitHub"
[5]: https://github.com/kotoba-tech/kotoba-whisper/blob/main/run_short_form_eval.py?utm_source=chatgpt.com "kotoba-whisper/run_short_form_eval.py at main · kotoba-tech/kotoba-whisper · GitHub"


RTFは単一のモデル固有定数ではなく、かなり多くの条件に依存します。特にASRでは、次の変数の影響が大きいです。

* **GPU性能**：T4 / L4 / 3090 / A100 / H100 など。Tensor Core性能、メモリ帯域、VRAM容量が効きます。
* **batch size**：最重要級です。batchを増やすとGPU利用率が上がり、throughput RTFは大きく改善します。ただし単発レイテンシは悪化することがあります。
* **音声長**：短いクリップは前処理・起動・kernel launchなどの固定オーバーヘッド比率が高く、RTFが悪化しやすいです。
* **モデル構造**：Whisperのようなautoregressive decoderは生成token数の影響を受けます。Parakeet TDT/CTCのような非自己回帰寄りの構造は一般に高速化しやすいです。
* **decoder設定**：greedy / beam search、beam width、TDT / CTC、timestamp生成など。探索が増えるほどRTFは悪化します。
* **dtype / quantization**：FP32、FP16、BF16、INT8など。GPUとの相性次第ですが、FP16/BF16/INT8でかなり改善する場合があります。
* **入力長の揃い方**：batch内で音声長がバラバラだとpaddingが増えて無駄な計算が増えます。length bucketingが効きます。
* **サンプリングレート**：16 kHzと48 kHzなど。モデル入力前に16 kHzへ落とす場合、その前処理時間をRTFに含めるかでも変わります。
* **前処理・後処理**：Opus decode、resample、VAD、normalization、tokenizer、timestamp整形、句読点付与など。
* **実装ライブラリ**：PyTorch / NeMo / Transformers / faster-whisper / TensorRT / ONNX Runtime など。同じ重みでもRTFはかなり変わります。
* **attention backend**：SDPA、FlashAttention、通常attentionなど。
* **CUDA/cuDNN/TensorRTバージョン**：kernel最適化や対応dtypeにより差が出ます。
* **CPU性能**：audio decode、feature extraction、DataLoaderがGPUのボトルネックになることがあります。
* **ディスク・ネットワークI/O**：ファイル読み込みまで計測範囲に入れる場合に効きます。
* **GPU warm/cold状態**：最初の数回はmodel load、CUDA context、kernel compilationなどで遅くなります。
* **並列ユーザー数**：Serverlessではdynamic batchingやqueueingによってthroughput RTFが改善する一方、ユーザー体感latencyは増えることがあります。
* **音声内容**：特にautoregressive ASRでは、発話量、無音量、生成token数、言語、timestamp生成などが処理時間に影響します。

今回の `parakeet-tdt_ctc-0.6b-ja` なら、特に見るべきなのはこの6つです。

| 変数                   | 重要度   |
| -------------------- | ----- |
| GPU種類                | ★★★★★ |
| batch size           | ★★★★★ |
| TDT / CTC decoder    | ★★★★★ |
| 音声長・length bucketing | ★★★★☆ |
| FP16/BF16等のprecision | ★★★★☆ |
| 前処理をRTFに含めるか         | ★★★★☆ |

そしてRTFには実務上、少なくとも2種類あります。

**Model RTF**

[
RTF_{model}=
\frac{\text{純粋なモデル推論時間}}
{\text{音声時間}}
]

これはモデル比較向けです。

一方、実際のPremiereサービス原価を見るなら、

[
RTF_{service}=
\frac{
T_{decode}
+T_{resample}
+T_{feature}
+T_{inference}
+T_{postprocess}
}
{T_{audio}}
]

の方が重要です。

さらに1000ユーザー規模のサービスでは、**batch=1のRTFよりもthroughput RTF**が重要になります。例えば、

```text
batch=1
RTF = 0.025

batch=32
RTF = 0.006
```

なら、ユーザー1人の単発処理は40倍速ですが、サーバー全体では約167倍速で処理できます。

したがってベンチマークでは、最低でも

```text
GPU
batch_size
decoder
precision
dataset
audio_duration
inference_seconds
RTF
RTFx
VRAM_peak
```

を記録してください。

特に今回の料金計算に使うRTFは、**「モデルカードに書かれたRTF」ではなく、本番予定のGPU・batch・decoder・Opus decode条件で測った `RTF_service`** を採用するのが最も正確です。


はい。今回の目的なら、**すべてのGPUを総当たりする必要はありません**。`nvidia/parakeet-tdt_ctc-0.6b-ja` は約0.6B規模なので、80GB級GPUよりも **16〜24GB級GPUでの「$/audio-hour」競争**を最優先に調べるべきです。

前提はこれまで通り、

* 1000ユーザー
* 1人最大60 audio-hours/月
* 合計 **60,000 audio-hours/月**
* Opus 24 kbpsでアップロード
* Parakeet TDTを主decoder
* SaaS側ではbatching可能

とします。

Hugging Face Inference Endpointsでは現在T4 $0.50/h、L4 $0.70〜0.80/h、A10G $1.00/h、L40S $1.80/h、A100 $2.50/hなどが利用できます。([Hugging Face][1]) RunPod Podsでは現在A5000 $0.27/h、L4 $0.39/h、3090 $0.50/h、4090 $0.69/h、A40 $0.44/h、A6000 $0.53/h、L40S $0.99/hなどが掲載されています。([Runpod][2])

## まず調査すべきGPUの優先順位

私は次の順序にします。

| 優先    | サービス        | GPU           |       現行単価目安 | 調査理由              |
| ----- | ----------- | ------------- | -----------: | ----------------- |
| **S** | RunPod Pod  | A5000 24GB    |      $0.27/h | 最安候補              |
| **S** | RunPod Pod  | L4 24GB       |      $0.39/h | 推論性能/電力効率が強い      |
| **S** | RunPod Pod  | RTX 3090 24GB |      $0.50/h | FP16 throughput候補 |
| **S** | RunPod Pod  | RTX 4090 24GB |      $0.69/h | 高速性で単価差を逆転できる可能性  |
| **S** | HF Endpoint | T4 14/16GB    |      $0.50/h | HF最安基準            |
| **S** | HF Endpoint | L4 24GB       | $0.70–0.80/h | 本番HF候補            |
| A     | HF Endpoint | A10G 24GB     |      $1.00/h | L4との比較            |
| A     | RunPod Pod  | A40 48GB      |      $0.44/h | 非常に安価なAmpere候補    |
| A     | RunPod Pod  | A6000 48GB    |      $0.53/h | A40/3090比較        |
| B     | RunPod Pod  | L40S 48GB     |      $0.99/h | 高速上限確認            |
| B     | HF Endpoint | L40S 48GB     |      $1.80/h | HF高性能基準           |
| C     | RunPod/HF   | A100 80GB     |   $1.2〜2.5/h | 性能上限のreference    |

A100/H100は後回しで構いません。0.6B ASRではVRAMより**価格あたりTensor throughput**の方が重要だからです。

---

# 最初にやるべき「最小行列」

GPU 12種類 × batch 6種類 × decoder 2種類などを最初から全部やると無駄が多いので、3段階に分けます。

### Phase 1 — GPU選別

各GPUで、

```text
decoder   = TDT
precision = BF16 または FP16
batch     = 1, 8, 32
dataset   = 共通固定sample
```

だけ測ります。

優先6 GPUなら、

`6 GPUs × 3 batch = 18 runs`

です。

対象は、

```text
RunPod A5000
RunPod L4
RunPod 3090
RunPod 4090
HF T4
HF L4
```

これだけでかなり絞れます。

---

# Phase 2 — 上位3 GPUを詳しく調査

Phase 1で、

[
Cost/audio-hour
===============

GPU\ price/hour \times RTF
]

が良かった上位3種類だけ、

```text
batch = 1
        4
        8
        16
        32
        64
        最大OOM直前

decoder = TDT
          CTC

precision = FP16/BF16
```

まで展開します。

特に、

```text
batch=1
```

はユーザー体感latency用、

```text
batch=16〜64
```

は1000人SaaSの原価用です。

---

# Phase 3 — 実サービス条件

最後の1〜2 GPUについてだけ、

```text
Opus 24 kbps
↓
decode
↓
16 kHz mono
↓
dynamic batching
↓
Parakeet
↓
postprocess
↓
JSON
```

全部を含む `RTF_service` を測ります。

ここで初めて、

* cold start
* Opus decode
* CPU preprocessing
* queue
* batch scheduler
* GPU inference
* postprocessing

まで含めます。

---

# Datasetを何時間流せば十分か

RTFだけなら、CER測定ほど大量のデータは必要ありません。

私は次の基準を推奨します。

| 目的        |      必要音声量 |   ファイル数目安 |  繰返し |
| --------- | ---------: | --------: | ---: |
| 動作確認      |      5〜10分 |    50〜100 |   1回 |
| GPU粗選別    | **30〜60分** |   300〜600 |   3回 |
| RTF比較     |    **2時間** |  800〜1500 |   3回 |
| 本番候補確定    |    **5時間** | 2000〜4000 |   3回 |
| 最終CER+RTF |  全test set |    数千〜1万超 | 1〜3回 |

つまり、**Phase 1では1GPUあたり1時間程度で十分**です。

Phase 2では2時間。

最終候補だけ5時間以上です。

---

# なぜ1時間くらいでRTF比較できるのか

例えばRTF=0.02なら、1時間の音声処理は約72秒です。

3回測れば、

```text
Run 1  71.8 sec
Run 2  72.5 sec
Run 3  71.9 sec
```

のようにばらつきを評価できます。

これが、

```text
RTF
mean
stddev
p50
p95
```

として十分安定していれば、さらに10時間流してもGPUランキングが逆転する可能性は低くなります。

ただし、**音声長の分布を揃えること**の方が重要です。

---

# 「1時間分をランダムに取る」だけでは少し弱い

ASRではclip durationがRTFに影響するので、

```text
short
0〜5秒

medium
5〜15秒

long
15〜30秒
```

を含ませてください。

例えば1時間benchmarkなら、

| 長さ     |  割合 |
| ------ | --: |
| 0〜5秒   | 25% |
| 5〜10秒  | 30% |
| 10〜20秒 | 30% |
| 20〜30秒 | 15% |

程度にします。

実サービスではPremiere素材をVADでchunk化する可能性があるため、この分布は重要です。

---

# Kotoba評価datasetをどう使うか

3つとも性質が違うので、それを利用します。

### Common Voice

`japanese-asr/ja_asr.common_voice_8_0`

4,483 utterancesで、音声長は約1.6〜10.6秒です。([Hugging Face][3])

これは、

**短〜中clip throughput**

を見るのに非常に適しています。

---

### JSUT Basic5000

5,000 utterancesです。([Hugging Face][4])

元JSUT corpusは約10時間の音声です。([Hugging Face][5])

比較的きれいな読み上げ音声なので、

**モデルそのものの純粋なthroughput比較**

に適しています。

---

### ReazonSpeech test

5,263 utterances、約0.6〜29.7秒というかなり広いduration分布です。([Hugging Face][6])

テレビ・自然発話系なので、

**実サービスに一番近いRTF挙動**

を見るのに適しています。

---

# 私ならbenchmark subsetをこう作ります

3 datasetからそれぞれ、

```text
Common Voice    40 min
JSUT            40 min
ReazonSpeech    40 min
```

抽出します。

合計、

**2 audio-hours**

です。

ファイル数としてはおおよそ、

**800〜1500 files**

程度になれば十分です。

これを一度manifest化して、

```text
benchmark-v1.jsonl
```

として固定します。

すべてのGPUに**完全に同じファイル、同じ順序**を流します。

これが重要です。

---

# Phase 1ならもっと小さくてよい

GPUの粗選別なら、

```text
CV8        20 min
JSUT       20 min
Reazon     20 min

TOTAL      60 min
```

で十分です。

例えば6 GPU × batch 3種類でも、

18 runs × 1 audio-hour

です。

RTF=0.02なら純粋推論時間は1 run約72秒なので、非常に安く選別できます。

---

# 最終評価だけ全datasetを使う

CERを正式比較する段階ではsubsetではなく、

```text
Common Voice 8 test
JSUT Basic5000
ReazonSpeech test
```

を全部流してください。

Common Voiceは4,483件、JSUTは5,000件、ReazonSpeech testは5,263件です。([Hugging Face][3])

約15,000 utterancesあるので、

```text
CER
RTF
duration bucket別RTF
VRAM
throughput
```

をまとめて出せます。

---

# 1000ユーザー前提から必要throughputを逆算すると

月60,000 audio-hoursです。

1か月を730時間とすると、

[
60000/730 \approx 82.2
]

つまり平均して常時、

**82 audio-hours/hour**

処理する必要があります。

これは言い換えると、

**約82倍リアルタイムのaggregate throughput**

です。

GPU 1枚あたりの処理能力は、

[
RTFx=1/RTF
]

なので、

|   RTF | 1 GPU能力 | 平均必要GPU数 |
| ----: | ------: | -------: |
|  0.10 |     10× |      8.2 |
|  0.05 |     20× |      4.1 |
|  0.03 |     33× |      2.5 |
|  0.02 |     50× |     1.64 |
|  0.01 |    100× |     0.82 |
| 0.005 |    200× |     0.41 |

ここから、今回のベンチマークでかなり重要な目標が見えます。

**throughput RTF ≤ 0.02**

なら、平均負荷をL4/3090等 **2 GPU程度**で処理できる可能性があります。

ピークを平均の3倍と仮定しても、

```text
average  82× realtime
peak    ~246× realtime
```

なので、RTF=0.02なら約5 GPUです。

---

# したがって「調べる価値のある境界」

私は今回、次の判定を使います。

### 有望

```text
RTF <= 0.02
```

非常に有望。

### 許容

```text
0.02 < RTF <= 0.05
```

サービス化可能。

### 微妙

```text
0.05 < RTF <= 0.10
```

料金またはbatch最適化が必要。

### 除外候補

```text
RTF > 0.10
```

0.6Bモデルとしては、本番GPU候補として優先度を落とす。

---

# 特にRunPod Serverlessには注意点があります

RunPod Serverlessでは、

```text
L4
A5000
3090
```

が同じ24GB GPU poolとして扱われることがあります。RunPodはendpointで最大3種類のGPU priorityを指定できます。([Runpod Documentation][7])

したがって、

**Serverlessの「24GB pool」という名前だけでbenchmarkしない**

方がよいです。

まずPodで、

```text
A5000
L4
3090
```

を個別に測定します。

その後、

```text
RunPod Serverless AMPERE_24
```

を実サービス条件として測ります。

RunPod Serverlessでは現在24GB classが約$0.69/hです。([Runpod][8])

---

# 最終的に作るべき表

benchmark outputはこの形がおすすめです。

| Provider | GPU   |       $/h | Batch | Decoder | Precision | RTF | RTFx | $/audio-h | VRAM GB |
| -------- | ----- | --------: | ----: | ------- | --------- | --: | ---: | --------: | ------: |
| RunPod   | A5000 |      0.27 |     1 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | A5000 |      0.27 |     8 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | A5000 |      0.27 |    32 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | L4    |      0.39 |     1 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | L4    |      0.39 |     8 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | L4    |      0.39 |    32 | TDT     | FP16      |   … |    … |         … |       … |
| RunPod   | 3090  |      0.50 |     … | …       | …         |   … |    … |         … |       … |
| RunPod   | 4090  |      0.69 |     … | …       | …         |   … |    … |         … |       … |
| HF       | T4    |      0.50 |     … | …       | …         |   … |    … |         … |       … |
| HF       | L4    | 0.70–0.80 |     … | …       | …         |   … |    … |         … |       … |

ランキングに使う主指標は、

[
\boxed{
Cost_{audio-hour}
=================

Price_{GPU-hour}\times RTF_{service}
}
]

です。

## 私なら実際にはこう絞ります

最初のテストはわずかこの6種類で十分です。

```text
RunPod
├ A5000
├ L4
├ RTX 3090
└ RTX 4090

Hugging Face
├ T4
└ L4
```

各GPUについて、

```text
1 audio-hour
×
batch {1, 8, 32}
×
3 repetitions
```

を行います。

つまり1 GPU当たり **9 benchmark runs**。

ここで下位半分を切ります。

残った3 GPUだけ、

```text
2 audio-hours
×
batch {1,4,8,16,32,64}
×
TDT/CTC
```

へ進みます。

最終1〜2 GPUだけ**5時間以上＋全評価dataset＋Opus service path**を測れば十分です。

この方法なら、**大量のGPU時間を使わずに「1000ユーザーを最も安く処理できるGPU」をかなり高い確度で特定できます。** 最初からA100/H100まで総当たりするより、今回の0.6B ASRではこちらの方が合理的です。

[1]: https://huggingface.co/docs/inference-endpoints/pricing?utm_source=chatgpt.com "Pricing · Hugging Face"
[2]: https://www.runpod.io/product/cloud-gpus?utm_source=chatgpt.com "Cloud GPU Instances for AI Workloads | Runpod"
[3]: https://huggingface.co/datasets/japanese-asr/ja_asr.common_voice_8_0?utm_source=chatgpt.com "japanese-asr/ja_asr.common_voice_8_0 · Datasets at Hugging Face"
[4]: https://huggingface.co/datasets/japanese-asr/ja_asr.jsut_basic5000?utm_source=chatgpt.com "japanese-asr/ja_asr.jsut_basic5000 · Datasets at Hugging Face"
[5]: https://huggingface.co/datasets/FluidInference/JSUT-basic5000/blob/main/README_en.txt?utm_source=chatgpt.com "README_en.txt · FluidInference/JSUT-basic5000 at main"
[6]: https://huggingface.co/datasets/japanese-asr/ja_asr.reazonspeech_test?utm_source=chatgpt.com "japanese-asr/ja_asr.reazonspeech_test · Datasets at Hugging Face"
[7]: https://docs.runpod.io/serverless/endpoints/endpoint-configurations?utm_source=chatgpt.com "Endpoint settings - Runpod Documentation"
[8]: https://www.runpod.io/pricing?utm_source=chatgpt.com "GPU Cloud Pricing | Per-Second H100, A100, RTX | Runpod"

はい。**GitHub Actionsで十分実装可能**です。今回の用途では、GitHub Actionsを計測基盤そのものにせず、**RunPod/Hugging Face Jobsへベンチマークを一斉投入するオーケストレータ**にするのが最も扱いやすいです。

GitHub Actionsのmatrixは1 workflowあたり最大256 jobsを生成でき、`max-parallel`で同時実行数も制御できます。今回の `provider × GPU × batch × decoder` 程度なら余裕があります。([GitHub Docs][1])

## 推奨構成

```text
GitHub Actions
      │
      ├─ build benchmark image
      │       ↓
      │     GHCR
      │
      ├─ matrix生成
      │
      ├──────────────┬───────────────┐
      ↓              ↓               ↓
HF Jobs          RunPod Pod      RunPod Serverless
T4/L4/A10G       L4/3090/...       burst test
      │              │               │
      └──── benchmark.py ────────────┘
                     │
                     ↓
              result.json
                     │
                     ↓
          HF Bucket / S3 / R2
                     │
                     ↓
             GitHub Actions
                     │
            aggregate_results.py
                     ↓
       results.csv / summary.md
```

Hugging Face JobsはCLI、Python API、HTTP APIのいずれからでも起動でき、GPU flavorを指定した複数Jobの並列実行が公式にサポートされています。秒単位の従量課金です。([Hugging Face][2])

## matrixは「直積」にしない方がよい

例えば単純に、

```yaml
matrix:
  provider: [hf, runpod]
  gpu: [t4, l4, a5000, 3090, 4090]
  batch: [1, 8, 32]
```

とすると、

`2 × 5 × 3 = 30 jobs`

ですが、HFには3090がなく、RunPodには同じSKU名がない、といった無効組み合わせが発生します。

したがって `include:` で明示する方が安全です。

```yaml
strategy:
  fail-fast: false
  max-parallel: 6
  matrix:
    include:
      - provider: hf
        gpu: t4
        flavor: t4-small
        batch: 1

      - provider: hf
        gpu: t4
        flavor: t4-small
        batch: 8

      - provider: hf
        gpu: t4
        flavor: t4-small
        batch: 32

      - provider: hf
        gpu: l4
        flavor: l4
        batch: 1

      - provider: hf
        gpu: l4
        flavor: l4
        batch: 8

      - provider: hf
        gpu: l4
        flavor: l4
        batch: 32

      - provider: runpod
        gpu: l4
        batch: 1

      - provider: runpod
        gpu: l4
        batch: 8

      - provider: runpod
        gpu: l4
        batch: 32

      - provider: runpod
        gpu: rtx3090
        batch: 1

      - provider: runpod
        gpu: rtx3090
        batch: 8

      - provider: runpod
        gpu: rtx3090
        batch: 32
```

これならPhase 1のテストをそのまま表現できます。

---

# ベンチマーク本体を共通Docker imageにする

ここが一番重要です。

Providerごとに実装を変えず、

```text
ghcr.io/<owner>/parakeet-benchmark:<sha>
```

を両方で使います。

Docker内には、

```text
benchmark.py
requirements.lock
NeMo
PyTorch
ffmpeg
datasets
huggingface_hub
```

を固定します。

実行コマンドだけ、

```bash
python benchmark.py \
  --model nvidia/parakeet-tdt_ctc-0.6b-ja \
  --dataset-manifest benchmark-v1.jsonl \
  --batch-size 32 \
  --decoder tdt \
  --precision fp16 \
  --repeat 3 \
  --output result.json
```

とします。

これにより、

**HFとRunPodで違うのはGPUとProviderだけ**

になります。

これはベンチマークとして非常に重要です。

---

# Datasetも毎回ランダム抽出しない

先ほどの、

```text
Common Voice   20 min
JSUT           20 min
ReazonSpeech   20 min
```

合計1時間のPhase 1 datasetを一度作って、

```text
benchmark-v1.jsonl
```

として固定します。

例えば、

```json
{"dataset":"common_voice","path":"...","duration":7.32}
{"dataset":"jsut","path":"...","duration":11.82}
{"dataset":"reazon","path":"...","duration":18.14}
```

のようにします。

そうすると全GPUが完全に同じ音声を処理するため、

```text
RTF difference
=
ほぼGPU/Runtime差
```

にできます。

---

# HF Jobs側は非常に簡単

HF JobsではDocker imageとGPU flavorを指定して実行できます。公式CLIでは例えばA10Gを、

```bash
hf jobs run \
  --flavor a10g-small \
  ghcr.io/example/parakeet-bench@sha256:<immutable-digest> \
  python benchmark.py
```

のように起動できます。([Hugging Face][3])

また、

```bash
--detach
```

を付ければJob IDだけ取得して非同期に実行できます。

```bash
hf jobs wait "$JOB_ID"
```

で完了待ちもできます。複数Jobを並列に実行する用途もHF Jobs自体が想定しています。([Hugging Face][4])

したがってActionsでは、

```text
matrix job
 ↓
hf jobs run --detach
 ↓
JOB_ID
 ↓
hf jobs wait
 ↓
result download
```

でよいです。

---

# GitHub Actionsそのものは待ち続けさせない方法もある

設計として2種類あります。

### 方法A：Actions jobがGPU job終了まで待つ

シンプルです。

```text
Actions
 ↓
HF Job作成
 ↓
wait
 ↓
結果取得
```

Phase 1程度ならこれで十分です。

---

### 方法B：dispatchとcollectを分ける

大規模化するならこちらです。

```text
benchmark-dispatch.yml
       ↓
GPU jobsだけ発行
       ↓
job IDs保存

benchmark-collect.yml
       ↓
status確認
       ↓
results収集
```

GitHub Actions runnerを長時間占有しません。

今回の1〜2時間audio benchmarkなら、実推論自体が十分高速であれば、まずAで問題ありません。

---

# 結果はGitHub Artifactだけに依存しない方がよい

GPU workerはGitHub runnerではないので、

```text
GPU
↓
actions/upload-artifact
```

を直接するのは面倒です。

そこで私は以前のHF buckets設計と同じく、

```text
results/
  benchmark-id/
    hf-t4-b1.json
    hf-t4-b8.json
    hf-t4-b32.json
    runpod-l4-b1.json
    runpod-l4-b8.json
    ...
```

をHF Bucket/S3/R2へ書かせます。

各JSONには、

```json
{
  "model": "nvidia/parakeet-tdt_ctc-0.6b-ja",
  "provider": "runpod",
  "gpu": "NVIDIA L4",
  "batch_size": 32,
  "decoder": "tdt",
  "precision": "fp16",
  "audio_seconds": 3604.82,
  "elapsed_seconds": 21.41,
  "rtf": 0.00594,
  "rtfx": 168.37,
  "peak_vram_gb": 11.8,
  "cer": 0.071,
  "gpu_price_hour": 0.39,
  "cost_per_audio_hour": 0.00232
}
```

のように記録します。

最後にActionsが全部読み込みます。

---

# 最後にランキングを自動生成

集計scriptは、

```python
cost_per_audio_hour = gpu_price_per_hour * rtf
```

を計算し、

```text
provider
gpu
batch
RTF
RTFx
CER
VRAM
$/GPU-h
$/audio-h
estimated monthly GPUs
estimated monthly cost
```

でソートします。

1000ユーザー前提なら月60,000 audio-hoursなので、

```python
monthly_gpu_hours = 60000 * rtf
monthly_cost = monthly_gpu_hours * gpu_price
```

です。

例えばRTF=0.006、$0.39/hなら、

```text
60,000 × 0.006
= 360 GPU-h/month

360 × $0.39
= $140.40/month
```

となります。

ここまで自動化してしまうと、benchmark終了後GitHub Actions Summaryに、

| Rank | Provider | GPU  | Batch |   RTF | $/audio-h | 60k h/月 |
| ---: | -------- | ---- | ----: | ----: | --------: | ------: |
|    1 | RunPod   | L4   |    32 | 0.006 |  $0.00234 |    $140 |
|    2 | RunPod   | 3090 |    32 | 0.005 |  $0.00250 |    $150 |
|    3 | HF       | T4   |    32 | 0.011 |  $0.00550 |    $330 |

のような表を出せます。

---

# GitHub Actions workflowの構造

私は3 workflowに分けます。

```text
.github/workflows/

benchmark-build.yml
benchmark-phase1.yml
benchmark-full.yml
```

### `benchmark-build.yml`

```text
benchmark code変更
↓
Docker build
↓
GHCR push
```

---

### `benchmark-phase1.yml`

```text
workflow_dispatch
 ↓

Prepare manifest

 ↓

matrix:
 HF T4
 HF L4
 RunPod A5000
 RunPod L4
 RunPod 3090
 RunPod 4090

 × batch 1/8/32

 ↓

18 benchmarks

 ↓

Aggregate

 ↓

ranking
```

---

### `benchmark-full.yml`

Phase 1の上位候補だけ手動入力します。

```yaml
workflow_dispatch:
  inputs:
    gpu1:
    gpu2:
    gpu3:
```

そして、

```text
batch 1,4,8,16,32,64
×
TDT/CTC
×
3 repetitions
```

を回します。

---

# GitHub Matrixの最大数にも十分収まる

GitHub Actions matrixは現在1 workflow runにつき最大256 jobです。([GitHub Docs][1])

例えばPhase 2を、

```text
3 GPUs
×
6 batches
×
2 decoders
×
2 precisions
×
3 repetitions
=
216 jobs
```

としてもギリギリ1 matrix内に収まります。

ただしこれは**一斉に216 GPUを立てるという意味ではありません**。

```yaml
strategy:
  max-parallel: 6
```

などにして、

**最大同時GPU数を6台**

に制限するべきです。

これは予算事故防止にも非常に重要です。

---

# ただしrepeatはmatrixにしなくてよい

216 jobsまで膨らませるより、

```text
1 GPU job

benchmark
 run 1
 run 2
 run 3
```

と1 workerの中で3回測る方がよいです。

理由は、

* cold startを毎回含めない
* model downloadを繰り返さない
* GPU個体差を減らせる
* 課金が減る

ためです。

したがって実際には、

```text
3 GPU
× 6 batch
× 2 decoder
× 2 precision

= 72 GPU jobs
```

程度にします。

---

## 私なら今回この構成にします

```text
                 GitHub Actions
                       │
               benchmark matrix
                       │
           max-parallel = 4〜6
             ┌─────────┴─────────┐
             │                   │
          HF Jobs             RunPod
             │                   │
             └─────────┬─────────┘
                       │
             same GHCR image
                       │
             same benchmark-v1
                       │
                     GPU
                       │
                result.json
                       │
                  HF Bucket
                       │
                aggregate.py
                       │
        ┌──────────────┴──────────────┐
        │                             │
 benchmark-results.csv       GitHub Summary
        │
        └──→ $/audio-hour ranking
```

これは今回の目的にかなり合っています。

特に**GitHub Actions → GHCR → HF Jobs/RunPod → HF Bucket → Actions集計**にしておくと、前に検討していたVast/RunPod/HF Jobsのインフラ設計とも共通化しやすく、将来Vast.aiを3番目のProviderとして加える場合もadapterを1つ追加するだけで済みます。([Hugging Face][2])

[1]: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax?utm_source=chatgpt.com "Workflow syntax for GitHub Actions - GitHub Docs"
[2]: https://huggingface.co/docs/hub/jobs?utm_source=chatgpt.com "Jobs · Hugging Face"
[3]: https://huggingface.co/docs/huggingface_hub/guides/jobs?utm_source=chatgpt.com "Run and manage Jobs · Hugging Face"
[4]: https://huggingface.co/docs/hub/jobs-overview?utm_source=chatgpt.com "Jobs Overview · Hugging Face"


はい。前に提案した**Phase 1の一斉ベンチマーク**なら、驚くほど安く済みます。

現在の公式価格は、Hugging Face JobsがT4-small **$0.40/h**、L4 **$0.80/h**。RunPod PodはA5000 **$0.27/h**、L4 **$0.39/h**、RTX 3090 **$0.50/h**、RTX 4090 **$0.69/h**です。HF JobsはStarting/Running中を分単位で課金します。 ([Hugging Face][1])

## Phase 1の条件

前に決めた条件をそのまま使います。

```text
GPU:
  RunPod: A5000, L4, 3090, 4090
  HF:     T4, L4

batch:
  1, 8, 32

各Job:
  1 audio-hour × 3回
```

したがって、

* RunPod: 4 GPU × 3 batch = **12 Jobs**
* HF: 2 GPU × 3 batch = **6 Jobs**
* 合計: **18 Jobs**

です。

### 純推論時間だけの場合

| 仮RTF | RunPod 12 Jobs | HF 6 Jobs |        合計 |
| ---: | -------------: | --------: | --------: |
| 0.01 |          $0.17 |     $0.11 | **$0.27** |
| 0.02 |          $0.33 |     $0.22 | **$0.55** |
| 0.05 |          $0.83 |     $0.54 | **$1.37** |

かなり安いです。

理由は、RTF=0.02なら1時間音声の推論に必要なのは約72秒だからです。

---

## 現実には起動・モデルロード時間がかかる

短時間ベンチではこちらの方が効きます。

仮に各Jobごとに、

```text
container start
model download/cache
NeMo initialization
CUDA warmup
dataset preparation
```

で**5分固定オーバーヘッド**が発生すると仮定します。

すると、

| 仮RTF | RunPod | HF Jobs |    **総額** |
| ---: | -----: | ------: | --------: |
| 0.01 |  $0.63 |   $0.41 | **$1.04** |
| 0.02 |  $0.80 |   $0.52 | **$1.31** |
| 0.05 |  $1.30 |   $0.84 | **$2.14** |

したがってPhase 1は、かなり保守的に見ても、

> **$1〜$3程度**

を予算にしておけば十分そうです。

ただし初回Docker pullやモデルDLが極端に遅い場合は多少増えます。

---

# Provider別に見ると

RTF=0.02＋5分オーバーヘッドで、

### RunPod

| GPU      |      単価 | 3 batch合計概算 |
| -------- | ------: | ----------: |
| A5000    | $0.27/h |      約$0.12 |
| L4       | $0.39/h |      約$0.17 |
| RTX 3090 | $0.50/h |      約$0.22 |
| RTX 4090 | $0.69/h |      約$0.30 |
| **合計**   |         |  **約$0.80** |

RunPodの現行Pod価格はこの水準です。 ([Runpod][2])

### Hugging Face Jobs

| GPU      |      単価 | 3 batch合計概算 |
| -------- | ------: | ----------: |
| T4-small | $0.40/h |      約$0.17 |
| L4       | $0.80/h |      約$0.34 |
| **合計**   |         |  **約$0.52** |

HF JobsはT4-small $0.40/h、L4 $0.80/hです。 ([Hugging Face][1])

---

# Phase 2もそれほど高くありません

Phase 2では上位3 GPUだけを、

```text
batch:
1, 4, 8, 16, 32, 64

decoder:
TDT
CTC

dataset:
2 audio-hours

repeat:
3
```

とすると、

```text
3 GPUs
× 6 batch
× 2 decoder
=
36 Jobs
```

です。

1 Jobあたり、

```text
2 audio-hours × 3 repeats
=
6 audio-hours
```

処理します。

仮に上位3 GPUを、

* RunPod A5000
* RunPod L4
* RunPod 4090

と仮定すると、

|  RTF |  純推論費 |    5分起動込み |
| ---: | ----: | --------: |
| 0.01 | $0.97 | **$2.32** |
| 0.02 | $1.94 | **$3.29** |
| 0.05 | $4.86 | **$6.21** |

です。

つまりPhase 2でも、

> **$3〜$7くらい**

の予算でかなり詳細な比較ができます。

---

# Phase 1 + Phase 2

例えばRTF=0.02付近なら、

```text
Phase 1   ≈ $1.31
Phase 2   ≈ $3.29
────────────────
合計      ≈ $4.60
```

です。

かなり安い。

さらに最終候補2 GPUについて5時間datasetを回したとしても、ASRモデルが十分高速なら**総ベンチマーク予算$10〜$20程度**でもかなり広範囲に評価できる可能性があります。

---

# 実際には「GPU計算費」よりモデルロード時間対策が重要

今回のような0.6B ASRでは推論が高速なので、

```text
GPU inference  2〜5分

model download 5分
container pull 3分
NeMo startup   1分
```

となると、本体より準備時間の方が高くつきます。

そのため、

```text
1 Job
 ↓
model load once
 ↓
batch=1 benchmark
 ↓
batch=8 benchmark
 ↓
batch=32 benchmark
```

と、**GPUごとにbatchを1 Job内で連続測定する**方がさらに安くできます。

この形ならPhase 1は、

```text
現在:
6 GPUs × 3 batch
= 18 Jobs

改善:
6 GPUs
= 6 Jobs
```

です。

起動回数が1/3になります。

RTF=0.02・起動5分なら、Phase 1全体は概算で**$0.8前後まで下がる**可能性があります。

---

## 私なら予算枠をこう置きます

| 段階         | 目的                    |          予算目安 |
| ---------- | --------------------- | ------------: |
| Smoke test | Docker/NeMo動作確認       |            $1 |
| Phase 1    | 6 GPU粗選別              |        **$2** |
| Phase 2    | 上位3 GPU詳細評価           |    **$5〜$10** |
| Final      | 上位1〜2 GPU、5h+全dataset |       $10〜$20 |
| **全体**     | GPU選定完了               | **$20〜$30程度** |

これはかなり余裕を持たせた予算です。

特に今回のParakeet 0.6Bでは、**A100/H100を長時間借りるLLMベンチとは違って、GPU選定そのものの実験費は非常に小さい**と考えてよいです。

なおRunPod Serverlessを使う場合は料金体系がPodと異なり、現在L4/A5000/3090 24GBクラスはflex workerで$0.00019/sです。今回のようなGPU種類別比較では、まず通常PodでGPU型を固定して測り、最終的にServerless構成を別途測る方が比較としてきれいです。 ([docs.runpod.io][3])

[1]: https://huggingface.co/docs/hub/en/jobs-pricing?utm_source=chatgpt.com "Pricing and Billing · Hugging Face"
[2]: https://www.runpod.io/pricing?utm_source=chatgpt.com "GPU Cloud Pricing | Per-Second H100, A100, RTX | Runpod"
[3]: https://docs.runpod.io/serverless/pricing?utm_source=chatgpt.com "Pricing - Runpod Documentation"


事前チャージ額としては、**Hugging Faceに $10、RunPodに $20** 入れておけば、今回のPhase 1 → Phase 2 → Finalまでかなり余裕を持って回せると考えます。

現在、HF JobsはT4-smallが **$0.40/h**、L4が **$0.80/h**で、Starting/Running中のみ分単位課金です。Jobs利用には正のクレジット残高が必要です。([Hugging Face][1]) RunPodはA5000 $0.27/h、L4 $0.39/h、3090 $0.50/h、4090 $0.69/h程度で、Podは秒課金です。([Runpod][2])

| サービス              | 純ベンチ概算 | 起動・DL・再試行込みの現実的想定 | **推奨事前チャージ** |
| ----------------- | -----: | ----------------: | -----------: |
| Hugging Face Jobs |  約$2〜5 |             約$5〜8 |      **$10** |
| RunPod            | 約$5〜12 |           約$10〜15 |      **$20** |
| **合計**            |      — |           約$15〜23 |      **$30** |

ここで想定しているのは、Phase 1で6 GPU候補を粗選別し、Phase 2で上位3候補をbatch/decoder別に詳細測定し、Finalで1〜2 GPUについて5時間以上または全dataset評価を行う構成です。推論が想定より速ければ、実際にはこの金額をかなり下回る可能性があります。

特にRunPodについては、公式ドキュメント上も**新規評価なら$10程度から開始可能**で、クレジットは前払い・払い戻し不可です。([Runpod Documentation][3]) そのため、最初から大量に入れる必要はありません。

私なら実際には、

```text
Hugging Face : $10
RunPod       : $20
─────────────────
Total        : $30
```

にします。

これなら失敗ジョブ、Docker/model初回pull、NeMo初期化、batch=64でOOMして再試行、といった実験時の無駄も十分吸収できます。

さらに慎重に始めるなら、**HF $5 + RunPod $10 = $15**でもPhase 1〜Phase 2くらいまでは十分狙えます。ただしRunPodはPod起動時に選択構成の最低1時間分のcredit残高が必要です。([Runpod Documentation][4])

したがって、今回のベンチマーク一式を途中で残高不足にせず回す目的なら、**$30合計を事前チャージの基準額**にするのが扱いやすいです。

[1]: https://huggingface.co/docs/hub/jobs-pricing?utm_source=chatgpt.com "Pricing and Billing · Hugging Face"
[2]: https://www.runpod.io/pricing?utm_source=chatgpt.com "GPU Cloud Pricing | Per-Second H100, A100, RTX | Runpod"
[3]: https://docs.runpod.io/accounts-billing/billing?utm_source=chatgpt.com "Billing overview - Runpod Documentation"
[4]: https://docs.runpod.io/pods/pricing?utm_source=chatgpt.com "Pricing - Runpod Documentation"


はい。**RunPodのベンチマーク費用が高く見えたことと、本番でRunPodの方が安くなる可能性は矛盾しません。** 理由は、ベンチ時と本番時で「何にお金を払っているか」が違うからです。

まず今回のベンチでは、RunPod側でA5000・L4・3090・4090など複数GPUを試す想定だった一方、HF側は主にT4・L4でした。つまり単純に**RunPodの方が試験ケース数が多かった**ため、ベンチ総額が高く見えています。個々のGPU時間単価だけを比較すると、RunPod Podは現在A5000 $0.27/h、L4 $0.39/h、3090 $0.50/h、4090 $0.69/hで、HF JobsはT4-small $0.40/h、L4 $0.80/hです。 ([Runpod][1])

本番で重要なのは、この式です。

[
\boxed{\text{Cost/audio-hour}=\text{GPU価格/時}\times RTF}
]

たとえば同じParakeetを測って、

| 構成          | GPU単価 |  仮RTF | 1 audio-hour原価 |
| ----------- | ----: | ----: | -------------: |
| HF T4       | $0.40 | 0.030 |        $0.0120 |
| HF L4       | $0.80 | 0.015 |        $0.0120 |
| RunPod L4   | $0.39 | 0.015 |   **$0.00585** |
| RunPod 4090 | $0.69 | 0.007 |   **$0.00483** |

となったとします。

この場合、HF T4はGPU自体は安いですが、RunPod 4090はGPU単価が高くてもRTFが大幅に良いため、**音声1時間を処理する原価はRunPod 4090の方が約60%安い**ということになります。

### 特にRunPod L4とHF L4は分かりやすい

同じNVIDIA L4なら、基本的にモデル側のRTFは大きくは変わらないと期待できます。

現在、

* HF Jobs L4: **$0.80/h**
* RunPod Pod L4: **$0.39/h**

です。 ([Hugging Face][2])

仮に両方RTF=0.02なら、

[
HF = 0.80 \times 0.02 = $0.016/audio\text{-}h
]

[
RunPod = 0.39 \times 0.02 = $0.0078/audio\text{-}h
]

なのでRunPodは**約半額**です。

1000ユーザー・月60,000 audio-hoursなら、

| 構成                 | 月GPU時間 | 概算GPU費/月 |
| ------------------ | -----: | -------: |
| HF L4, RTF=.02     | 1,200h |     $960 |
| RunPod L4, RTF=.02 | 1,200h | **$468** |

となります。

年間では約$5,900程度の差です。

---

## RunPodのもう一つの強みはGPU選択肢

HF Jobsは現在T4、L4、A10G、L40S、A100、H200などを提供しています。 ([Hugging Face][2])

一方RunPodには、

* A5000
* L4
* RTX 3090
* RTX 4090
* RTX 5090
* A40
* A6000
* L40/L40S
* A100/H100

など、特に**コンシューマー/ワークステーション系GPU**が多くあります。 ([Runpod Documentation][3])

今回のParakeetは0.6B級なので、A100/H100の巨大VRAMはあまり必要ありません。

そのため、

```text
大規模LLM
→ H100/A100の価値が高い

Parakeet 0.6B
→ 24GB GPUで十分
→ 3090 / 4090 / L4 / A5000が価格競争力を持つ
```

という事情があります。

ここがRunPodと非常に相性がよいところです。

---

## 特に4090が面白い

4090は現在RunPod Podで約$0.69/hです。 ([Runpod][1])

HF L4 $0.80/hより**時間単価そのものも安い**うえ、Parakeetのような比較的小さなFP16/BF16推論で4090のRTFがL4より良ければ、

```text
安い
+
速い
```

の両方を取れる可能性があります。

だからベンチマークで4090を入れているわけです。

反対にデータセンターGPUであるL4は、

* 安定性
* 電力効率
* 動画エンコード
* server inference用途

などの特性を持つので、4090が必ず勝つということでもありません。

だからこそ実測RTFが必要です。

---

# Serverlessだけなら必ずしもRunPodが安いわけではない

ここは重要な修正点です。

RunPod Serverlessの24GBクラス、

```text
L4 / A5000 / 3090
```

は現在flex workerで約 **$0.69/h**、active workerなら約$0.47/h相当です。 ([Runpod Documentation][4])

一方、HF Jobs T4は$0.40/hです。 ([Hugging Face][2])

したがって、

```text
RunPod Serverless L4/A5000/3090
vs
HF Jobs T4
```

なら、GPU時間単価だけではHF T4の方が安いです。

ただし、

```text
HF T4 RTF = 0.04

RunPod 24GB pool RTF = 0.015
```

なら、

```text
HF:
0.40 × .04
= $0.016/audio-h

RunPod:
0.69 × .015
= $0.01035/audio-h
```

となり、やはりRunPodが逆転します。

結局は**RTF込み**です。

---

# 1000ユーザーになると「常駐Pod」が効く

今回の仮定では月60,000 audio-hoursです。

RTF=0.02なら、

[
60000\times0.02=1200 GPU\ hours/month
]

必要です。

これは平均すると、

[
1200/730\approx1.64 GPU
]

です。

つまりサービスが軌道に乗ると、

**GPUをほぼ常時1〜2枚使う負荷**

になります。

この段階になると、

```text
Serverless
```

より、

```text
常駐RunPod Pod
```

が合理的になる可能性が高くなります。

RunPod L4を仮に2枚常時置けば、

[
2\times730\times$0.39
\approx $569/月
]

です。 ([Runpod][1])

そしてピーク時だけServerlessを足す、

```text
          normal load
              ↓
       RunPod Pod ×2

peak ─────────────→ Serverless burst
```

という構成ができます。

これが今回かなり有力です。

---

# HFは管理コストの低さに価値がある

一方、HF Jobsは単純に「GPU単価が高いサービス」と見るべきではありません。

HF JobsはDocker imageとhardware flavorを指定してJobsを実行でき、Starting/Running時間だけ課金されます。モデルがHF Hub上にある場合も開発体験が統一されています。 ([Hugging Face][2])

つまり、

```text
HF Hub
+
HF model
+
HF datasets
+
HF Jobs
```

という統合があります。

なので、

**運用工数を含めたTCO**

ではHFが有利になる場合もあります。

例えば月にGPU費を$300節約しても、その代わりRunPodのworker管理や障害対応に毎月何時間も使うなら、初期段階ではHFの方が合理的です。

---

# 今回のサービスなら段階的に変えるのがよい

私は次の構成が一番自然だと思います。

### 0〜100 users

```text
HF Jobs
または
RunPod Serverless
```

固定費を持たない。

### 100〜500 users

```text
RunPod Serverless
+
必要に応じてPod
```

### 500〜1000+ users

```text
RunPod Pod
      ↓
base load

+
Serverless
      ↓
burst
```

です。

つまり、

> **HF = 開発・実験・低トラフィックで非常に使いやすい**

> **RunPod = 負荷が安定して大量になるほどGPU単価最適化の自由度が効く**

という違いです。

---

## 今回ベンチマークする本当の目的

したがって「RunPodが安いはずだからRunPodを選ぶ」のではありません。

調べたいのは、

[
\boxed{
\frac{$}{audio\ hour}
}
]

です。

特に今回なら、

```text
HF T4
HF L4

vs

RunPod A5000
RunPod L4
RunPod 3090
RunPod 4090
```

を測定して、

| Provider | GPU   |  $/h | RTF | **$/audio-h** |
| -------- | ----- | ---: | --: | ------------: |
| HF       | T4    | 0.40 |   ? |             ? |
| HF       | L4    | 0.80 |   ? |             ? |
| RunPod   | A5000 | 0.27 |   ? |             ? |
| RunPod   | L4    | 0.39 |   ? |             ? |
| RunPod   | 3090  | 0.50 |   ? |             ? |
| RunPod   | 4090  | 0.69 |   ? |             ? |

を完成させます。 ([Hugging Face][2])

**この最後の列が最小のGPUが本番候補です。**

そして1000ユーザー規模では、さらに

[
MonthlyCost
===========

60,000\times RTF\times GPUPrice
]

まで自動計算すれば、サービス選択を感覚ではなく実測値で決められます。

なので今回RunPodに少し多めにベンチ予算を割くのは、**費用が高いからではなく、安くなる可能性のあるGPU候補がHFより多いため、それを探索する費用**だと考えるのが正確です。

[1]: https://www.runpod.io/pricing?utm_source=chatgpt.com "GPU Cloud Pricing | Per-Second H100, A100, RTX | Runpod"
[2]: https://huggingface.co/docs/hub/jobs-pricing?utm_source=chatgpt.com "Pricing and Billing · Hugging Face"
[3]: https://docs.runpod.io/references/gpu-types?utm_source=chatgpt.com "GPU types - Runpod Documentation"
[4]: https://docs.runpod.io/serverless/pricing?utm_source=chatgpt.com "Pricing - Runpod Documentation"

少ないユーザー数でも**常にReady・低レイテンシ**を優先するなら、サービスイン時点では私は **Hugging Face Inference Endpointsを第一候補**にします。理由は、`min_replica=1` を維持して常時1台を起動しつつ、負荷増加時だけautoscaleできるからです。HF公式FAQでも、scale-to-zeroを許可しなければmin replica数だけ常時Availableになると明記されています。([Hugging Face][1])

特に今回の要件では、**HF JobsではなくInference Endpoints**を使うのがポイントです。

### サービス開始時の推奨

```text
Premiere UXP
    ↓
自前API/Auth
    ↓
HF Inference Endpoint
    ↓
Parakeet
```

Endpoint設定は例えば、

```text
GPU          : T4 または L4
min replicas : 1
max replicas : 2〜3
scale-to-zero: OFF
```

です。

HFはGPU利用率やpending requestを基準にautoscaleできるため、普段は1 GPUだけ維持し、ユーザーが増えたら2〜3 replicasへ自動拡張できます。([Hugging Face][2])

## なぜ初期はRunPod常駐PodよりHFを推すのか

RunPodの方がGPU単価自体は安くなる可能性があります。しかしサービスイン直後は、

```text
ユーザー数       少ない
GPU利用率        低い
要求             即応性重視
運用人員         少ない
```

という状態になりやすいです。

この段階では、

**GPU単価差より、常時Ready + autoscaling + endpoint管理の容易さ**

の価値が高いです。

HF Inference Endpointsなら、

```text
常時1 replica
        ↓
request増加
        ↓
autoscale 2
        ↓
autoscale 3
        ↓
負荷低下
        ↓
1 replicaへ戻る
```

という構成をサービス側で持てます。([Hugging Face][2])

RunPodでももちろん実現できますが、

```text
Pod health
queue
routing
autoscaling
replacement
GPU availability
```

などをより自前で面倒を見る設計になりやすいので、初期サービスではHFの運用上の利点が大きいです。

## 固定費はどのくらいか

ここは重要です。

HF Inference Endpointを**常時1 replica**にすると、ユーザーが0人でもGPU代が発生します。

HF公式PricingではGPU Endpointの例として `$0.50/h` のGPUが示され、1 min replicaを常時稼働すると、

[
0.50\times730
=============

$365/月
]

です。HFはInitializingおよびRunning中を分単位で課金します。([Hugging Face][3])

つまり初期ユーザーが10人しかいなくても、

**約$365/月クラスの固定GPU費**

になる可能性があります。

仮にL4が$0.80/hなら、

[
0.80\times730
=============

$584/月
]

です。

これが「常時Ready」の価格です。

### 初期はT4がかなり有力

`parakeet-tdt_ctc-0.6b-ja` は0.6Bなので、最初からL4を常時起動する必要があるかはベンチ結果次第です。

例えば、

```text
HF T4
RTF = 0.03

HF L4
RTF = 0.015
```

だったとしても、ユーザーが少ない初期段階ではthroughputより**固定費**が重要になります。

仮に、

| 構成    | 常時費用/月 |   RTF |
| ----- | -----: | ----: |
| HF T4 |  約$365 |  0.03 |
| HF L4 |  約$584 | 0.015 |

なら、初期はT4の方が合理的です。

T4でも1 audio-hourを、

[
60min\times0.03=1.8min
]

程度で処理できるなら、UXPユーザー体験として十分速い可能性があります。

---

# RunPodが有利になるのはユーザー増加後

例えばRunPod L4が$0.39/hなら、常時1台で、

[
0.39\times730
\approx $285/月
]

です。

つまり同じL4クラスなら、RunPodの方が固定GPU費をかなり抑えられる可能性があります。

したがって、**最安固定費だけならRunPod Podも非常に有力**です。

私なら判断をこう分けます。

| 段階           | 推奨                          | 理由                   |
| ------------ | --------------------------- | -------------------- |
| 0〜数十users    | **HF Endpoint T4**          | 運用簡単、Ready、autoscale |
| 数十〜200users  | HF T4/L4またはRunPod L4        | 実測RTFで比較             |
| 200〜500users | RunPod常駐Podが有力              | GPU単価差が効き始める         |
| 500〜1000+    | **RunPod base Pod + burst** | 利用率を高く維持できる          |

これはユーザー数だけでなく、GPU利用率で判断するのがより正確です。

---

# Ready状態なら「Serverless scale-to-zero」は使わない

今回の希望からすると、

```text
HF scale-to-zero
RunPod Flex Serverless cold start
```

は主系統には向きません。

HFも公式に、scale-to-zeroからの復帰には数分かかる場合があり、レスポンシブな用途には一般に推奨しないと説明しています。([Hugging Face][4])

したがって、

```text
min replica = 1
```

を基本にするべきです。

---

# ただし「Ready GPU」と「Burst GPU」を分離すると非常に良い

最終的には、

```text
                    ┌─ HF/RunPod burst GPU
                    │
UXP → API → Queue ──┤
                    │
                    └─ always-ready GPU ×1
```

が良いです。

普段：

```text
Ready GPU ×1
```

だけ課金。

混雑すると、

```text
Ready GPU ×1
+
Burst ×N
```

へ増やします。

これなら「最初のユーザーを待たせない」と「ピークのためにGPUを常時5台置かない」を両立できます。

---

## サービスイン時点で私ならこうします

**第1候補**

```text
HF Inference Endpoint
Parakeet 0.6B
T4
min_replica = 1
max_replica = 2
scale-to-zero = OFF
```

です。

まずT4で実測して、

```text
batch=1 latency
RTF
peak VRAM
60分素材の処理時間
```

が十分なら、そのままサービス開始します。

T4が遅ければL4へ上げます。

そしてユーザー数・GPU utilizationが上がってきた段階で、

```text
HF Endpoint
        ↓
RunPod L4/4090常駐
```

へ移す判断をします。

モデル本体をHF Hub、推論containerを共通Dockerとしておけば、この移行はかなり容易です。

### 判断基準を1つ置くなら

常時GPU利用率が月平均で、

```text
< 20%
```

ならHFの運用簡便性を優先。

```text
20〜50%
```

になったらRunPodとのTCO比較。

```text
> 50%
```

が安定して続くなら、**RunPod常駐GPUへ移す経済的メリットがかなり大きくなる**

と考えます。

なので今回の要件では、**サービスイン直後＝HF Endpoint T4 always-ready、その後の実測需要に応じてRunPodへ移行**が、コスト・レスポンス・運用リスクのバランスが最も良いと思います。

[1]: https://huggingface.co/docs/inference-endpoints/guides/configuration?utm_source=chatgpt.com "Configuration · Hugging Face"
[2]: https://huggingface.co/docs/inference-endpoints/autoscaling?utm_source=chatgpt.com "Autoscaling · Hugging Face"
[3]: https://huggingface.co/docs/inference-endpoints/pricing?utm_source=chatgpt.com "Pricing · Hugging Face"
[4]: https://huggingface.co/docs/inference-endpoints/guides/autoscaling?utm_source=chatgpt.com "Autoscaling · Hugging Face"


はい。前提を「**常にReady状態を維持し、ユーザー増加に応じて運用コストを最適化する**」とすると、サービス選択はおおむね次のように推移すると考えるのが自然です。

| 実測需要の段階          |          月間利用量の目安 | 常時GPU利用率の目安 | 推奨構成                               | 選択理由                                | 次の移行トリガー                  |
| ---------------- | ----------------: | ----------: | ---------------------------------- | ----------------------------------- | ------------------------- |
| **サービス開始**       |  〜1,000 audio-h/月 |        〜10% | **HF Inference Endpoint T4 ×1**    | 常時Ready、管理が容易、autoscale可能           | T4の待ち行列が目立つ / 利用率20%超     |
| **初期成長**         |     1,000〜5,000 h |      10〜25% | **HF T4 ×1、必要時×2**                 | まだ運用工数を増やすよりHFのmanaged環境が有利         | 月額GPU費とRunPodとの差が無視できなくなる |
| **小規模安定**        |    5,000〜15,000 h |      20〜40% | **HF L4 ×1** または **RunPod L4 ×1**  | 実測RTFと$/audio-hで分岐                  | 常時利用率40〜50%超              |
| **中規模**          |   15,000〜30,000 h |      30〜60% | **RunPod L4/4090 常駐×1 + burst**    | 固定Podの安いGPU単価を活かしやすい                | ピーク時queue増加 / 平均必要GPU>1   |
| **成長期**          |   30,000〜60,000 h |      50〜80% | **RunPod 常駐×2 + Serverless burst** | base loadを安価なPodで処理し、ピークだけ増設        | 2台でも平均70〜80%超             |
| **1000 users想定** |       約60,000 h/月 |        構成依存 | **RunPod 2〜数台 + burst**            | steady workloadではPod単価差が大きく効く       | 平均/ピーク需要を再計測              |
| **大規模安定**        | 60,000〜120,000+ h |      60〜85% | **RunPod複数常駐 + autoscaling pool**  | GPU utilizationを高く維持して$/audio-hを最小化 | 専用契約/Vast/他cloud比較        |
| **Enterprise規模** |        120,000 h〜 |         高水準 | RunPod専用構成、複数provider、予約GPU等       | 価格だけでなく冗長性/SLAが重要                   | multi-cloud化              |

重要なのは、**ユーザー数より `audio-hours/月` とGPU utilizationで判断する**ことです。

たとえばユーザーが500人いても、

```text
平均 5 h/user/month
→ 2,500 audio-hours/month
```

しか使われないなら、HF Endpoint ×1で十分な可能性があります。

逆に100人でも、

```text
60 h/user/month
→ 6,000 audio-hours/month
```

なら、RunPodへの移行検討が早まります。

### 今回の想定を数値にすると

1000人 × 60時間/月なら、

[
60,000\ \text{audio-hours/month}
]

です。

仮に実測 `RTF_service = 0.02` なら、

[
60,000\times0.02=1,200\ GPUh/month
]

必要です。

平均必要GPU数は、

[
1,200/730 \approx 1.64
]

なので、

```text
サービス開始
HF T4 ×1
     │
     ▼
需要増加
HF T4/L4 ×1
     │
     ▼
steady workload発生
RunPod L4/4090 ×1
     │
     ▼
平均GPU需要 > 1
RunPod ×2
     │
     ├── 常時2 GPU
     │
     └── Serverless burst
```

という移行がかなり自然です。

### RTFによって移行時期は大きく変わる

60,000 audio-hours/月の場合：

|     実測RTF |  必要GPU時間/月 | 平均必要GPU数 | 想定構成          |
| --------: | ---------: | -------: | ------------- |
|     0.005 |       300h |     0.41 | 常時1 GPUでかなり余裕 |
|     0.010 |       600h |     0.82 | 常時1 GPU中心     |
| **0.020** | **1,200h** | **1.64** | 常時2 GPUが自然    |
|     0.030 |     1,800h |     2.47 | 2〜3 GPU       |
|     0.050 |     3,000h |     4.11 | 4〜5 GPU       |
|     0.100 |     6,000h |     8.22 | 8〜10 GPU級     |

つまり、今回予定しているParakeetベンチマークは単なるGPU比較ではなく、**「何ユーザーになったらHF→RunPodへ移すべきか」を決定する測定**にもなります。

実務では、私は次の**移行ルール**を設定しておくことを勧めます。

* **HF継続**：平均GPU利用率 < 20〜25%
* **HF vs RunPodを再計算**：25〜40%
* **RunPod常駐へ移行候補**：40〜50%以上が数週間継続
* **RunPod base + burst**：平均1GPUでは足りなくなった時点
* **複数常駐GPU**：平均需要が1.5 GPUを超えたあたり

つまり、サービス開始時には **HF Endpointを「低運用負荷で常時Readyを保証するために多少高く買う」**、需要が読めるようになったら **RunPodへ移してGPU利用率そのものを収益化する**、という考え方です。

今回のベンチマーク結果から `RTF_service` が確定すれば、この表をさらに**「月間利用者数 → 月額GPU費 → HF/RunPodの損益分岐ユーザー数」**まで具体的な数値にできます。


需要増加に伴う推奨インフラの変化

RTF=0.02を仮定した場合の月間音声処理量と平均必要GPU数の目安。

audioHours	avgGpu
1,000	0.03
5,000	0.14
15,000	0.41
30,000	0.82
60,000	1.64
120,000	3.29

はい。Marketplace配布なら、**ユーザーはCreative Cloud Desktop経由で最新版に更新できます**。AdobeはMarketplace pluginについて「ユーザーはCreative Cloud accountから常にlatest versionへアクセスできる」としており、Enterprise配布ではMarketplace pluginがCreative Cloud Desktop経由で自動更新されることも明記しています。([Adobe Developer][1])

ただし、**Endpoint切り替えのたびにUXP更新を配る設計にはしない方がよい**です。Marketplace更新はAdobeのレビュー・配布・ユーザー側更新状況に依存するため、即時のインフラ切替手段としては遅すぎます。Marketplace版UXPは「安定したbootstrap URL」だけを持ち、実際の推論Endpointはサーバー側で切り替える設計がおすすめです。

たとえばこうします。

```text
Premiere UXP
    │
    │ 固定
    ▼
https://api.example.com/v1/asr
    │
    ▼
Routing / Gateway
    │
    ├── HOT  : HF Endpoint
    │
    ├── WARM : RunPod L4
    │
    └── COLD : RunPod Serverless / fallback
```

UXPから見えるURLは常に、

```text
https://api.example.com/v1/asr
```

だけです。

裏側で、

```text
HF T4 → RunPod L4
```

に変えてもUXP更新は不要です。

## お考えのHot / Cold方式はかなり相性がよいです

例えばサービス開始時には、

| Role | Provider          | 状態      | 用途             |
| ---- | ----------------- | ------- | -------------- |
| HOT  | HF Endpoint T4    | 常時Ready | 通常リクエスト        |
| WARM | RunPod Pod        | 必要時起動   | 需要増加時          |
| COLD | RunPod Serverless | 通常停止    | burst/fallback |

としておきます。

需要が増えたら、

```text
Phase 1

HOT  = HF
COLD = RunPod
```

から、

```text
Phase 2

HOT  = RunPod
WARM = HF
```

へ切り替えられます。

UXP側には何の変更もありません。

---

## UXP内部にfallback endpointを持たせるのは「最後の保険」としては良い

例えば、

```ts
const ENDPOINTS = [
  "https://api.example.com/v1/asr",
  "https://backup.example.com/v1/asr"
];
```

のように2つ持たせる設計です。

ただし、

```text
UXP
 ├ primary endpoint
 ├ HF endpoint
 └ RunPod endpoint
```

のように**実GPU providerのURLを直接埋め込む**のは勧めません。

理由は、

* Provider変更のたびPlugin更新が必要
* API keyをUXPに置けない
* Provider構成が解析される
* rate limit/authの統一が難しい
* A/B routingが難しい

からです。

なのでfallbackも、

```text
Primary:
api.example.com

Fallback:
api-backup.example.com
```

までにします。

その先は両方ともあなたのcontrol planeです。

---

# さらに良いのはRemote Config

UXP内にはbootstrap URLだけ持たせて、

```text
UXP startup
    ↓
GET /v1/config
```

とします。

返却例：

```json
{
  "api_version": 1,
  "primary": "https://api.example.com/v1",
  "fallback": "https://api2.example.com/v1",
  "features": {
    "asr": true
  }
}
```

こうするとendpoint変更もPlugin update不要です。

さらに、

```json
{
  "routing": {
    "asr": "hot"
  }
}
```

などのlogical routingだけ返すようにもできます。

---

# Endpoint URLそのものさえRemote Configへ出さなくてもよい

実際にはもっと単純に、

```text
UXP
 ↓
api.example.com
```

だけ固定して、

Gateway内部で、

```text
request
 ↓
health check

HF healthy?
 ├ yes → HF
 └ no
      ↓
 RunPod healthy?
 ├ yes → RunPod
 └ no → queue/error
```

とするのが一番安定します。

Cloudflare Workers、AWS API Gateway + Lambda、Fly.io、小さなRust/Go APIなどで十分です。

この場合UXP側のEndpointは**製品寿命中ほぼ変更しません**。

---

## Hot / Cold切替はDNSだけに頼らない方がよい

例えば、

```text
asr.example.com
→ HF
```

から、

```text
asr.example.com
→ RunPod
```

へDNS変更する方法もあります。

ただしDNS cacheやTTLがあるため、秒単位のフェイルオーバーには向きません。

それより、

```text
api.example.com

           ┌ HF
Gateway ───┤
           └ RunPod
```

というApplication Layer routingの方が適しています。

---

# Hot / Coldを自動切替するなら

次のような指標を使えます。

```text
queue_depth
p95_latency
GPU_utilization
error_rate
request_rate
estimated_wait
provider_cost
```

例えば、

```text
if queue_depth > 20:
    activate RunPod

if p95_latency > 10s:
    add worker

if GPU utilization < 10% for 30min:
    remove worker
```

とできます。

さらにサービス移行時には、

```text
HF 100%
↓
HF 90% / RunPod 10%
↓
HF 50% / RunPod 50%
↓
HF 10% / RunPod 90%
↓
RunPod 100%
```

と**canary migration**できます。

これはMarketplace更新よりはるかに安全です。

---

# Marketplace自動更新は何に使うべきか

Marketplace updateは、

```text
UI変更
Premiere API対応
認証方式変更
新feature
manifest permissions
bug fix
```

には使います。

一方、

```text
GPU provider変更
HF → RunPod
RunPod → HF
L4 → 4090
model revision変更
autoscaling変更
traffic routing
```

には使わない方がよいです。

つまり、

```text
UXP version lifecycle
```

と、

```text
AI infrastructure lifecycle
```

を完全に分離します。

---

## 推奨アーキテクチャ

今回の構想なら、私は最終的にこうします。

```text
Adobe Marketplace
       │
       ▼
Premiere UXP
       │
       │ HTTPS
       ▼
api.yourdomain.com
       │
       ├ Auth
       ├ Subscription
       ├ Quota
       ├ Rate limit
       ├ Job queue
       └ Router
            │
      ┌─────┼─────────┐
      │     │         │
     HF   RunPod    Future provider
     HOT   WARM       COLD
      │     │         │
      └─────┴─────────┘
            │
        Parakeet
```

この構成なら、Marketplace版UXPが何か月更新されなくても、**バックエンドだけでHF→RunPod→別Providerへ移行できます**。

さらにUXP内部には、

```text
primary API domain
+
backup API domain
```

の2つだけ持たせます。

例えば、

```text
api.example.com
api-backup.example.com
```

です。

これなら万一メインGateway自体が落ちてもfallbackできます。

結論として、**Marketplaceの更新機構は存在しますが、Endpoint運用の仕組みとしては使わず、UXPには自社の固定API Endpointを置き、その裏側でHot/Warm/Cold GPU Providerを切り替える設計が最も堅牢です。** Adobe Marketplace版は最新バージョンをCreative Cloud Desktop経由で提供できますが、インフラ切替をMarketplace更新に依存させるべきではありません。([Adobe Developer][1])

[1]: https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/adobe-marketplace/?utm_source=chatgpt.com "Adobe Creative Cloud Marketplace"

Adobeは**UXPから外部Web APIへ接続する仕組み自体は公式サポート**していますが、あなたのプラグイン用の「bootstrap URLをAdobeがホスティングしてくれる」仕組みは、Premiere UXP/Marketplaceの標準機能としては提供されていません。UXPでは `fetch` / XHR / WebSocket が使え、接続先ドメインを `manifest.json` の `requiredPermissions.network.domains` に明示する方式です。([Adobe Developer][1])

したがって、今回なら **自分が恒久的に管理できる独自ドメイン**をbootstrap URLにするのが一番良いです。

例えば、

```text
https://api.example.com
```

または設定専用に、

```text
https://bootstrap.example.com
```

を取ります。

私は後者より、さらに安定した**API Gatewayの固定URL**を1本持つ構成を推します。

```text
Premiere UXP
     │
     │ ずっと同じURL
     ▼
https://api.example.com/v1
     │
     ├── auth
     ├── config
     ├── quota
     ├── routing
     └── jobs
           │
           ├── HF Endpoint
           ├── RunPod
           └── 将来のProvider
```

こうすれば「bootstrap URL」という特別な仕組みすら必要なくなります。

### UXP側

`manifest.json` は例えば、

```json
{
  "requiredPermissions": {
    "network": {
      "domains": [
        "https://api.example.com"
      ]
    }
  }
}
```

です。

Premiere UXPは、manifestに宣言されていないドメインへの通信を拒否します。Adobeは具体的なドメイン指定だけでなくワイルドカードもサポートしています。([Adobe Developer][1])

したがって将来的に、

```text
api.example.com
bootstrap.example.com
backup.example.com
```

を使い分ける可能性があるなら、

```json
{
  "requiredPermissions": {
    "network": {
      "domains": [
        "https://*.example.com"
      ]
    }
  }
}
```

という方法もあります。Adobe公式ドキュメントでもサブドメインに対するワイルドカード指定例があります。トップレベルドメイン部分へのワイルドカードには制限があります。([Adobe Developer][1])

## どこでホストするか

このbootstrap/API GatewayはGPUを必要としません。非常に軽い処理なので、候補としては次のようになります。

| 候補                       | 今回との相性 | 特徴                                    |
| ------------------------ | ------ | ------------------------------------- |
| **Cloudflare Workers**   | ★★★★★  | 軽量API・routing・低運用負荷                   |
| AWS Lambda + API Gateway | ★★★★☆  | 高信頼・機能豊富                              |
| Google Cloud Run         | ★★★★☆  | 普通のHTTP serviceを置きやすい                 |
| Fly.io                   | ★★★★☆  | Rust/Go serverをそのまま動かしやすい             |
| Vercel Functions         | ★★★☆☆  | 簡単だが今回にはややWeb frontend寄り              |
| 自前VPS                    | ★★★☆☆  | 安いが運用責任が増える                           |
| HF Space                 | ★★☆☆☆  | モデルデモには便利だがcontrol planeの恒久URLには優先しない |
| RunPod                   | ★☆☆☆☆  | GPU inference用。bootstrapには過剰          |

今回なら私は **Cloudflare Workers +独自ドメイン** を第一候補にします。

理由はbootstrap側では、

```text
GET /v1/config
POST /v1/jobs
GET /v1/jobs/{id}
```

程度しか必要なく、GPU処理そのものはHF/RunPodへ渡すからです。

例えば、

```text
api.yourproduct.com
        │
        ▼
Cloudflare Worker
        │
        ├── HF HOT
        └── RunPod COLD/WARM
```

という形です。

## Remote Configを使うなら

UXPに固定するのは、

```text
https://api.example.com
```

だけにして、

```http
GET /v1/config
```

から例えば、

```json
{
  "apiVersion": 1,
  "model": "parakeet-ja-v1",
  "features": {
    "asr": true
  },
  "limits": {
    "maxUploadSeconds": 14400
  }
}
```

を返します。

ただし、私は**実際のHF/RunPod endpoint URLをここでUXPへ返す必要もない**と思います。

むしろ、

```text
UXP
 ↓
api.example.com
 ↓
Router
 ↓
HF / RunPod
```

にして、Provider情報はサーバー側だけに持たせた方が安全です。

### 例えば切替時

最初：

```text
api.example.com
      ↓
HF Endpoint
```

ユーザー増加後：

```text
api.example.com
      ↓
RunPod L4
```

さらに障害時：

```text
api.example.com
      ↓
HF health NG
      ↓
RunPod fallback
```

UXPには何も変化しません。

---

## bootstrap自体の障害に備える

ここはお考えのfallback方式を使う価値があります。

UXP側に、

```text
Primary
https://api.example.com

Fallback
https://api-backup.example.com
```

だけは埋め込んでおく。

例えば、

```ts
const API_ROOTS = [
  "https://api.example.com",
  "https://api-backup.example.com",
];
```

とします。

そして、

```text
api.example.com
     ↓ timeout

api-backup.example.com
     ↓
same control plane
```

とします。

ただしこの2つを**同じCloudflare account・同じWorkerに完全依存**させると、見かけ上2つでもfailure domainは同じです。

本気で冗長化するなら、

```text
Primary
Cloudflare Workers

Fallback
AWS Lambda / Cloud Run
```

という別failure domainにします。

サービス開始段階ではそこまでやらず、

```text
Primary domain
+
backup subdomain
```

でも十分だと思います。

---

## Marketplace審査上はどうか

Marketplace配布だから外部APIを使えないという制約ではありません。Premiere UXPは明示的にWeb APIへの通信を公式サポートしており、Marketplace版でもmanifest permissionsの仕組みは同じです。Marketplaceそのものはプラグインの配布・更新・課金を担います。([Adobe Developer][1])

重要なのは、

```text
network: all
```

を安易に指定せず、

```text
https://api.example.com
```

のように**必要最小限のドメインだけ許可すること**です。

Adobe自身もmanifest permissionについて、将来的にユーザーが権限に同意する可能性を踏まえ、必要な権限だけ正確に指定することを推奨しています。([Adobe Developer][2])

したがってMarketplace提出時にも、

```json
"domains": "all"
```

より、

```json
"domains": [
  "https://api.example.com",
  "https://api-backup.example.com"
]
```

の方が設計としてきれいです。

## 今回ならこの形がおすすめです

```text
                    Adobe Marketplace
                           │
                           ▼
                     Premiere UXP
                           │
                  manifest allow-list
                           │
                           ▼
              https://api.example.com
                           │
                ┌──────────┴──────────┐
                │                     │
            Auth/Quota             Router
                                      │
                         ┌────────────┼────────────┐
                         │            │            │
                       HF          RunPod       Future
                      HOT           WARM         COLD
```

そしてUXP内に固定するものは、

```text
api.example.com
api-backup.example.com
```

まで。

**`*.hf.space`、Hugging Face Endpoint URL、RunPod Endpoint IDなどはUXPへ直接固定しない**方がよいです。

この設計なら、Adobe Marketplaceの更新頻度とは無関係に、モデル変更、GPU変更、HF→RunPod移行、Hot/Cold切替、canary routingをすべてバックエンド側で行えます。

なので今回のbootstrap URLに対する答えを一言でまとめると、**Adobe提供URLを探すのではなく、製品専用の独自ドメインを一本取得して、それを長期不変のAPI入口にするのが最適**です。Adobeはその外部API通信をUXPのmanifest network permissionとして正式にサポートしています。([Adobe Developer][1])

[1]: https://developer.adobe.com/premiere-pro/uxp/resources/recipes/network/?utm_source=chatgpt.com "Network Operations"
[2]: https://developer.adobe.com/premiere-pro/uxp/plugins/concepts/manifest/?utm_source=chatgpt.com "Plugin manifest"
