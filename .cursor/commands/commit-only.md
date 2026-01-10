# コミットのみ（現在のブランチ）

## 概要

現在のブランチに対して、ローカルの変更をコミットだけ行うためのシンプルなコマンドです。  
リモートへのプッシュやブランチ戦略（main 直コミット禁止など）は扱わず、**コミットメッセージ規約に沿ったコミット**だけを行います。

## 前提条件

- 変更済みファイルが存在すること
- コミットメッセージの具体的な書き方は、`.cursor/rules/commit-message-format.mdc` などで定義された規約に従うこと

## 実行手順（対話なし）

1. 未コミット差分を確認し、コミットメッセージの内容を検討する（例：`git diff` や `git diff --cached`）
2. 変更のステージング（`git add -A`）
3. コミット（環境変数または引数でメッセージを渡す）

### A) 安全な一括実行（メッセージ引数版）

```bash
MSG="<Prefix>: <サマリ（命令形/簡潔に）>" \
git add -A && \
git commit -m "$MSG"
```

例：

```bash
MSG="fix: 不要なデバッグログ出力を削除" \
git add -A && \
git commit -m "$MSG"
```

### A-2) 一時ファイルから読み込む（PowerShell/改行問題回避）

PowerShellで改行を含む文字列を扱う際の問題を回避するため、コミットメッセージを一時ファイルに書き出してから読み込む方法です。

**Bashでの例:**

```bash
# 一時ファイルにコミットメッセージを書き出す
cat > tools/git/tools/git/commit_msg.txt <<'EOF'
fix: 不要なデバッグログ出力を削除

- ユーザー情報取得処理の冗長なログ行を削除
- 必要な情報は残しつつログボリュームを削減
EOF

# 一括実行
git add -A && \
git commit -F tools/git/tools/git/commit_msg.txt

# 一時ファイルを削除
rm tools/git/tools/git/commit_msg.txt
```

**PowerShellでの例:**

```powershell
# 一時ファイルにコミットメッセージを書き出す
@"
fix: 不要なデバッグログ出力を削除

- ユーザー情報取得処理の冗長なログ行を削除
- 必要な情報は残しつつログボリュームを削減
"@ | Out-File -FilePath tools/git/commit_msg.txt -Encoding UTF8

# 一括実行
git add -A
git commit -F tools/git/commit_msg.txt

# 一時ファイルを削除
Remove-Item tools/git/commit_msg.txt
```

> **注意:** `git commit -F` オプションを使用することで、ファイルからコミットメッセージを読み込めます。これにより、PowerShellでの文字化けリスクを回避できます。

### B) ステップ実行（読みやすさ重視）

```bash
# 1) 差分を確認
git status
git diff

# 2) 変更をステージング
git add -A

# 3) コミット（メッセージを編集）
git commit -m "<Prefix>: <サマリ（命令形/簡潔に）>"
```

## ノート

- コミットメッセージのフォーマットやメッセージ生成の原則は、`.cursor/rules/commit-message-format.mdc` のルールに従ってください。
- ブランチ戦略（例：main 直コミット禁止、作業用ブランチ運用）やリモートへのプッシュ (`git push`) は、このコマンドの対象外です。必要に応じて、プロジェクトごとの README / CONTRIBUTING / 別コマンドで定義してください。


