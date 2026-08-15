#

## config/models
また、Parakeetについては**default = "ctc"を意図的に設定**しています。元モデルそのものはTDT-CTC hybridですが、今回のONNX/Rust開発ではまずCTCを成立させ、その後TDTへ広げるためです。これは上流モデルのdefault decoderを書き換えているのではなく、このRepositoryにおけるdeployment defaultという意味です。上流モデル自体はHybrid FastConformer TDT-CTCとして提供されています。
