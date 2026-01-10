# コミット＆プッシュ（現在のブランチ）

## 概要

現在のブランチに対して変更をコミットし、リモートへプッシュするための汎用的なコマンド例です。  
main/master への直接プッシュ禁止や、コミット前に実行する品質チェック（lint / test / build など）は、各プロジェクトのポリシーに応じてこのテンプレートを調整してください。

## 前提条件

- 変更済みファイルが存在すること
- リモート `origin` が設定済みであること

## 実行手順（対話なし）

1. ブランチ確認（main/master 直プッシュ防止）
2. 必要に応じて品質チェック（lint / test / build など）を実行
3. 変更のステージング（`git add -A`）
4. コミット（引数または環境変数のメッセージ使用）
5. プッシュ（`git push -u origin <current-branch>`）

## 使い方

### A) 安全な一括実行（メッセージ引数版）

```bash
MSG="<Prefix>: <サマリ（命令形/簡潔に）>" \
BRANCH=$(git branch --show-current) && \
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then \
  echo "⚠️ main/master への直接プッシュは禁止です"; exit 1; \
fi

# 任意の品質チェック（必要な場合のみ）
# 例:
# ./scripts/lint.sh && ./scripts/test.sh && ./scripts/build.sh || exit 1

git add -A && \
git commit -m "$MSG" && \
git push -u origin "$BRANCH"
```

例：

```bash
MSG="fix: 不要なデバッグログ出力を削除" \
BRANCH=$(git branch --show-current) && \
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then \
  echo "⚠️ main/master への直接プッシュは禁止です"; exit 1; \
fi

# 任意の品質チェック（必要な場合のみ）
# ./scripts/quality-check.sh || exit 1

git add -A && git commit -m "$MSG" && git push -u origin "$BRANCH"
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
BRANCH=$(git branch --show-current) && \
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then \
  echo "⚠️ main/master への直接プッシュは禁止です"; exit 1; \
fi

# 任意の品質チェック（必要な場合のみ）
# ./scripts/quality-check.sh || exit 1

git add -A && \
git commit -F tools/git/tools/git/commit_msg.txt && \
git push -u origin "$BRANCH"

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
$BRANCH = git branch --show-current
if ($BRANCH -eq "main" -or $BRANCH -eq "master") {
    Write-Host "⚠️ main/master への直接プッシュは禁止です"
    exit 1
}

# 任意の品質チェック（必要な場合のみ）
# ./scripts/quality-check.sh

git add -A
git commit -F tools/git/commit_msg.txt
git push -u origin $BRANCH

# 一時ファイルを削除
Remove-Item tools/git/commit_msg.txt
```

> **注意:** `git commit -F` オプションを使用することで、ファイルからコミットメッセージを読み込めます。これにより、PowerShellでの文字化けリスクを回避できます。

### B) ステップ実行（読みやすさ重視）

```bash
# 1) ブランチ確認
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "⚠️ main/master への直接プッシュは禁止です"; exit 1;
fi

# 2) 任意のローカル品質チェック（必要に応じて追加）
# 例:
# echo "品質チェック実行中..."
# ./scripts/lint.sh && ./scripts/test.sh && ./scripts/build.sh || exit 1

# 3) 変更をステージング
git add -A

# 4) コミット（メッセージを編集）
git commit -m "<Prefix>: <サマリ（命令形/簡潔に）>"

# 5) プッシュ
git push -u origin "$BRANCH"
```

## ノート

- コミットメッセージのフォーマットやメッセージ生成の原則は、`.cursor/rules/commit-message-format.mdc` などの規約に従ってください。
- 先に `git status` や `git diff` で差分を確認してからの実行を推奨します。
