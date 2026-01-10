# Issue作成

## 概要

GitHubリポジトリに対してIssueを作成するためのコマンド例です。  
タイトルのみ、またはタイトルと本文の両方を指定してIssueを作成できます。  
PowerShellでの文字化けリスクを回避するため、一時ファイルから読み込む方法も推奨しています。

## 前提条件

- GitHub CLI (`gh`) がインストール済みであること
- GitHub CLI が認証済みであること（`gh auth status` で確認）
- リポジトリがGitHub上に存在し、適切な権限があること

## 実行手順（対話なし）

1. Issueタイトルと本文を準備（必要に応じて一時ファイルに書き出す）
2. GitHub CLI でIssue作成（`gh issue create`）

## 使い方

### A) 最小限の情報で実行（タイトルのみ）

タイトルのみを指定してIssueを作成します。本文は空になります。

```bash
# タイトルのみ指定
TITLE="feat: 新機能の追加"

# Issue作成
gh issue create --title "$TITLE"
```

例：

```bash
TITLE="fix: ログ出力の文字化け問題を修正" \
gh issue create --title "$TITLE"
```

### A-2) 一時ファイルからタイトルを読み込む（PowerShell/改行問題回避）

PowerShellで改行を含む文字列を扱う際の問題を回避するため、タイトルを一時ファイルに書き出してから読み込む方法です。

**Bashでの例:**

```bash
# 一時ファイルにタイトルを書き出す
cat > tools/git/issue_title.txt <<'EOF'
fix: ログ出力の文字化け問題を修正
EOF

# Issue作成
gh issue create --title "$(cat tools/git/issue_title.txt)"

# 一時ファイルを削除
rm tools/git/issue_title.txt
```

**PowerShellでの例:**

```powershell
# 一時ファイルにタイトルを書き出す
@"
fix: ログ出力の文字化け問題を修正
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline

# Issue作成
$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create --title $title

# 一時ファイルを削除
Remove-Item tools/git/issue_title.txt
```

> **注意:** PowerShellでは `Get-Content` の `-Raw` オプションでファイル全体を読み込み、`.Trim()` で末尾の改行を削除します。`-NoNewline` オプションで書き込み時の末尾改行を防ぐこともできます。

### B) タイトルと本文を指定

タイトルと本文の両方を指定してIssueを作成します。

```bash
# 変数設定
TITLE="feat: 新機能の追加"
BODY=$(cat <<'EOF'
## 概要
このIssueでは、新しい機能を追加するための要件を定義します。

## 要件
- 機能Aの実装
- 機能Bの実装

## 関連情報
- 参考資料: [リンク](https://example.com)
EOF
)
# 注意: <<'EOF' (引用符あり) はヒアドキュメント内の変数展開を無効にします。
# Issue本文に変数を含めたい場合は、<<EOF (引用符なし) を使用してください。

# Issue作成
gh issue create --title "$TITLE" --body "$BODY"
```

> **推奨:** PowerShellから実行する場合は、文字化けリスクを回避するため、**B-2) 一時ファイルから読み込む方法**を使用してください。

### B-2) タイトルと本文を一時ファイルから読み込む（PowerShell/改行問題回避）

PowerShellで改行を含む文字列を扱う際の問題を回避するため、タイトルと本文を一時ファイルに書き出してから読み込む方法です。

**Bashでの例:**

```bash
# 一時ファイルにタイトルと本文を書き出す
cat > tools/git/issue_title.txt <<'EOF'
feat: 新機能の追加
EOF

cat > tools/git/issue_body.txt <<'EOF'
## 概要
このIssueでは、新しい機能を追加するための要件を定義します。

## 要件
- 機能Aの実装
- 機能Bの実装

## 関連情報
- 参考資料: [リンク](https://example.com)
EOF

# Issue作成
gh issue create --title "$(cat tools/git/issue_title.txt)" --body-file tools/git/issue_body.txt

# 一時ファイルを削除
rm tools/git/issue_title.txt tools/git/issue_body.txt
```

**PowerShellでの例:**

```powershell
# 一時ファイルにタイトルと本文を書き出す
@"
feat: 新機能の追加
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline

@"
## 概要
このIssueでは、新しい機能を追加するための要件を定義します。

## 要件
- 機能Aの実装
- 機能Bの実装

## 関連情報
- 参考資料: [リンク](https://example.com)
"@ | Out-File -FilePath tools/git/issue_body.txt -Encoding UTF8

# Issue作成
$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create --title $title --body-file tools/git/issue_body.txt

# 一時ファイルを削除
Remove-Item tools/git/issue_title.txt, tools/git/issue_body.txt
```

> **注意:** `gh issue create` には `--title-file` オプションはありませんが、ファイルから読み込んで `--title` に渡すことができます。`Get-Content` の `-Raw` オプションでファイル全体を読み込み、`.Trim()` で末尾の改行を削除します。

### C) ラベルやアサインを指定

ラベルやアサインを指定してIssueを作成します。

```bash
# 変数設定
TITLE="bug: バグの修正"
BODY="バグの詳細説明..."

# Issue作成（ラベルとアサインを指定）
gh issue create \
  --title "$TITLE" \
  --body "$BODY" \
  --label "bug,priority:high" \
  --assignee "@me"
```

**PowerShellでの例（一時ファイル使用）:**

```powershell
# 一時ファイルにタイトルと本文を書き出す
@"
bug: バグの修正
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline

@"
バグの詳細説明...
"@ | Out-File -FilePath tools/git/issue_body.txt -Encoding UTF8

# Issue作成
$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create `
  --title $title `
  --body-file tools/git/issue_body.txt `
  --label "bug,priority:high" `
  --assignee "@me"

# 一時ファイルを削除
Remove-Item tools/git/issue_title.txt, tools/git/issue_body.txt
```

### D) ステップ実行（デバッグ用）

```bash
# 1) GitHub CLI の認証状態を確認
echo "認証状態を確認中..."
gh auth status

# 2) リポジトリ情報を確認
echo "リポジトリ情報:"
gh repo view

# 3) タイトルと本文を準備（一時ファイルに書き出す）
cat > tools/git/issue_title.txt <<'EOF'
feat: 新機能の追加
EOF

cat > tools/git/issue_body.txt <<'EOF'
## 概要
このIssueでは、新しい機能を追加するための要件を定義します。
EOF

# 4) Issue作成
echo "Issue作成中..."
gh issue create --title "$(cat tools/git/issue_title.txt)" --body-file tools/git/issue_body.txt

# 5) 一時ファイルを削除
rm tools/git/issue_title.txt tools/git/issue_body.txt
echo "完了"
```

**PowerShellでの例:**

```powershell
# 1) GitHub CLI の認証状態を確認
Write-Host "認証状態を確認中..."
gh auth status

# 2) リポジトリ情報を確認
Write-Host "リポジトリ情報:"
gh repo view

# 3) タイトルと本文を準備（一時ファイルに書き出す）
@"
feat: 新機能の追加
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline

@"
## 概要
このIssueでは、新しい機能を追加するための要件を定義します。
"@ | Out-File -FilePath tools/git/issue_body.txt -Encoding UTF8

# 4) Issue作成
Write-Host "Issue作成中..."
$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create --title $title --body-file tools/git/issue_body.txt

# 5) 一時ファイルを削除
Remove-Item tools/git/issue_title.txt, tools/git/issue_body.txt
Write-Host "完了"
```

## オプション

`gh issue create` コマンドで使用できる主なオプション：

- `--title <string>`: Issueタイトル（必須）
- `--body <string>`: Issue本文
- `--body-file <file>`: Issue本文をファイルから読み込む
- `--label <labels>`: ラベルをカンマ区切りで指定（例: `"bug,priority:high"`）
- `--assignee <logins>`: アサインするユーザーをカンマ区切りで指定（例: `"@me,username"`）
- `--milestone <name>`: マイルストーンを指定
- `--project <name>`: プロジェクトを指定

## ノート

- Issueタイトルは簡潔で明確に記述することを推奨します。
- Issue本文は、必要に応じて構造化フォーマット（概要、要件、関連情報など）を使用すると読みやすくなります。
- PowerShellから実行する場合は、文字化けリスクを回避するため、**一時ファイルから読み込む方法（A-2、B-2）**を強く推奨します。
- GitHub CLI の認証が必要な場合は、`gh auth login` を実行してください。

## トラブルシューティング

### GitHub CLI が認証されていない場合

```bash
# 認証を開始
gh auth login

# 認証状態を確認
gh auth status
```

### リポジトリが認識されない場合

```bash
# 現在のリポジトリを確認
git remote -v

# GitHub CLI でリポジトリを確認
gh repo view
```

### 文字化けが発生する場合

PowerShellから実行する場合は、必ず一時ファイルを使用してください。

```powershell
# 正しい方法（一時ファイルを使用）
@"
タイトル
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline
$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create --title $title
Remove-Item tools/git/issue_title.txt

# 避けるべき方法（直接変数に代入）
$title = "タイトル"  # 文字化けの可能性あり
gh issue create --title $title
```

### Issue作成後にURLを取得

```bash
# Issue作成と同時にURLを取得
gh issue create --title "$TITLE" --body "$BODY" --web
# --web オプションでブラウザで開くことも可能
```

## 実行例

```bash
# 例1: タイトルのみでIssue作成
TITLE="docs: READMEの更新" \
gh issue create --title "$TITLE"

# 例2: タイトルと本文を指定（一時ファイル使用）
cat > tools/git/issue_title.txt <<'EOF'
feat: ユーザー認証機能の追加
EOF

cat > tools/git/issue_body.txt <<'EOF'
## 概要
ユーザー認証機能を追加します。

## 要件
- ログイン機能
- ログアウト機能
- セッション管理
EOF

gh issue create --title "$(cat tools/git/issue_title.txt)" --body-file tools/git/issue_body.txt
rm tools/git/issue_title.txt tools/git/issue_body.txt
```

**PowerShellでの例:**

```powershell
# 例1: タイトルのみでIssue作成
$title = "docs: READMEの更新"
gh issue create --title $title

# 例2: タイトルと本文を指定（一時ファイル使用）
@"
feat: ユーザー認証機能の追加
"@ | Out-File -FilePath tools/git/issue_title.txt -Encoding UTF8 -NoNewline

@"
## 概要
ユーザー認証機能を追加します。

## 要件
- ログイン機能
- ログアウト機能
- セッション管理
"@ | Out-File -FilePath tools/git/issue_body.txt -Encoding UTF8

$title = (Get-Content tools/git/issue_title.txt -Raw).Trim()
gh issue create --title $title --body-file tools/git/issue_body.txt
Remove-Item tools/git/issue_title.txt, tools/git/issue_body.txt
```

## 関連ドキュメント

- GitHub CLI 公式ドキュメント: <https://cli.github.com/manual/gh_issue_create>
- GitHub CLI リファレンス: <https://cli.github.com/manual/gh_issue>

