# iPhone Stock Watch

iPhone 18 Pro Max 256GB ブラック（MJX54J/A / JAN 4549995734546）の在庫監視用リポジトリです。

## GitHub Actions監視
5分間隔で次の3店舗を確認します。

- ヤマダウェブコム
- ケーズデンキ
- ヨドバシカメラ

ページ取得には Jina Reader を使い、商品型番周辺の価格・在庫表示を判定します。
AmazonなどGitHub側で安定取得できない店舗は、このリポジトリでは通知対象にしません。

## 通知
Android の ntfy に通知します。
通知トピックはリポジトリには保存せず、GitHub Actions Secret `NTFY_TOPIC` から読み込みます。

## 実行間隔
GitHub Actions の混雑を避けるため、毎時 2・7・12・17・22・27・32・37・42・47・52・57 分に実行する設定です。
GitHubのスケジュール実行は遅延・欠落することがあるため、厳密な5分保証ではありません。
