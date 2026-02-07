# OCHシフトくん

医師の希望入力 → 管理者が作成 → 完成版を共有、までをシンプルに回すための最小構成Webアプリです。

## 使い方（ローカル）

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

起動後、`http://127.0.0.1:8000` にアクセス。

## 画面

- `/input` 希望入力
- `/admin` 管理（希望一覧、Codex用プロンプト、完成版保存）
- `/view` 完成版の共有表示

## データ保存

- `och_shiftkun.db` にSQLiteで保存されます。

## 運用の流れ

1. 各医師が `/input` で希望を入力
2. 管理者が `/admin` で希望一覧を確認
3. Codex用プロンプトをコピーして勤務表を作成
4. 完成版（表＋回数表＋変更ログ）を `/admin` で保存
5. `/view` をURL共有
