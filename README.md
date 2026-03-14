# BGM Remover

動画ファイルからBGM（背景音楽）を自動除去し、ボーカルや効果音のみの映像を出力するGUIツールです。

## 機能

- 動画ファイルからBGMを除去してボーカル・効果音のみの映像を出力
- GPU / CPU の切り替えによる処理速度の最適化
- 複数ファイルの一括処理（サブフォルダも再帰的にスキャン）
- 5種類のAI分離モデルから選択可能
- 起動時に `audio-separator` の最新バージョンを自動チェック

## 対応形式

`.mp4` / `.mkv` / `.avi` / `.mov`

## 使用モデル

| モデル名 | 備考 |
|---|---|
| `UVR-MDX-NET-Inst_HQ_3.onnx` | デフォルト・高品質 |
| `UVR-MDX-NET-Inst_Main.onnx` | |
| `UVR_MDXNET_Main.onnx` | |
| `UVR_MDXNET_KARA_2.onnx` | カラオケ向け |
| `Kim_Inst.onnx` | |

## 処理フロー

1. 動画から音声を抽出（WAV形式）
2. AIモデルでBGMと音声を分離（audio-separator）
3. ffmpegの`amix`フィルタでBGMを減算
4. 分離した音声と映像を再合成（AAC 192kbps）
5. 出力ファイル名: `{元ファイル名}_nobgm.mp4`

## 起動方法

`run_bgm_remover.bat` をダブルクリックするだけで起動できます。

初回起動時に以下を自動で行います:

- Python 仮想環境（venv）の作成
- 依存ライブラリの自動インストール
- NVIDIA GPU の自動検出と CUDA 対応ランタイムのインストール

```
run_bgm_remover.bat
```

## 必要な環境

- Python 3.10 以上
- ffmpeg（PATH に登録済みであること）
- NVIDIA GPU（オプション・CPU でも動作可）

### ffmpeg のインストール

[ffmpeg 公式サイト](https://ffmpeg.org/download.html) からダウンロードし、実行ファイルのあるディレクトリを環境変数 `PATH` に追加してください。

## ファイル構成

```
BGM_Remover/
├── main.py               # エントリポイント
├── gui.py                # GUIメインクラス（customtkinter）
├── separator.py          # BGM分離ロジック
├── ffmpeg_utils.py       # ffmpeg操作ユーティリティ
├── requirements.txt      # 依存ライブラリ一覧
└── run_bgm_remover.bat   # 全自動ランチャー
```

## 依存ライブラリ

- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) - モダンなGUIフレームワーク
- [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) - ffmpegのPythonバインディング
- [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) - AIによる音声分離

## 手動インストール

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

GPU（CUDA）を使用する場合は、追加で以下を実行してください:

```bash
pip install audio-separator[gpu]
```
